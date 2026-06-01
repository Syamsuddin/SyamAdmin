"""
Sprint 1 — Unit tests untuk PeFi collectors dan aggregation.
Semua shell command di-mock sehingga test berjalan di macOS tanpa Ubuntu tools.
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Set dummy env agar import tidak crash
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "999")

from modules.pefi import PreEmptiveFirewall


def _make_pefi(db_path: str) -> PreEmptiveFirewall:
    """Buat instance PeFi dengan semua dependency di-mock."""
    executor = MagicMock()
    firewall = MagicMock()
    brain = MagicMock()
    notifier = MagicMock()
    return PreEmptiveFirewall(
        executor=executor,
        firewall=firewall,
        brain=brain,
        notifier=notifier,
        db_path=db_path,
        config={"PEFI_ENABLED": "true", "PEFI_INTERVAL": "60"},
    )


def _mock_exec(stdout: str = "", returncode: int = 0):
    """Helper: return executor.run mock dengan output tertentu."""
    async def _run(*args, **kwargs):
        return {"stdout": stdout, "stderr": "", "returncode": returncode, "success": returncode == 0}
    return _run


class TestParsers(unittest.TestCase):
    """Test helper parser methods."""

    def test_parse_ipv4_from_peer(self):
        self.assertEqual(PreEmptiveFirewall._parse_ip_from_peer("1.2.3.4:54321"), "1.2.3.4")

    def test_parse_ipv6_from_peer(self):
        self.assertEqual(PreEmptiveFirewall._parse_ip_from_peer("[::1]:54321"), "::1")

    def test_parse_wildcard_returns_none(self):
        self.assertIsNone(PreEmptiveFirewall._parse_ip_from_peer("*"))
        self.assertIsNone(PreEmptiveFirewall._parse_ip_from_peer("-"))
        self.assertIsNone(PreEmptiveFirewall._parse_ip_from_peer(""))

    def test_parse_port_from_addr(self):
        self.assertEqual(PreEmptiveFirewall._parse_port_from_addr("0.0.0.0:80"), 80)
        self.assertEqual(PreEmptiveFirewall._parse_port_from_addr(":::443"), 443)
        self.assertIsNone(PreEmptiveFirewall._parse_port_from_addr("noport"))


class TestTrustedCheck(unittest.TestCase):
    """Test _is_trusted() untuk IP lokal dan whitelist."""

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name)

    def test_loopback_trusted(self):
        self.assertTrue(self.pefi._is_trusted("127.0.0.1"))

    def test_private_rfc1918_trusted(self):
        self.assertTrue(self.pefi._is_trusted("192.168.1.100"))
        self.assertTrue(self.pefi._is_trusted("10.0.0.1"))
        self.assertTrue(self.pefi._is_trusted("172.16.5.5"))

    def test_public_ip_not_trusted(self):
        self.assertFalse(self.pefi._is_trusted("1.2.3.4"))
        self.assertFalse(self.pefi._is_trusted("8.8.8.8"))

    def test_whitelist_cache(self):
        self.pefi._whitelist_cache.add("5.5.5.5")
        self.assertTrue(self.pefi._is_trusted("5.5.5.5"))


class TestCollectConnections(unittest.IsolatedAsyncioTestCase):
    """Test _collect_connections() dengan output ss yang di-mock."""

    # Format nyata ss -tn state established (Ubuntu):
    # State  Recv-Q  Send-Q  Local:Port  Peer:Port
    SS_ESTABLISHED = """\
State   Recv-Q  Send-Q  Local Address:Port  Peer Address:Port
ESTAB   0       0       10.0.0.1:80         1.2.3.4:54321
ESTAB   0       0       10.0.0.1:443        1.2.3.4:54322
ESTAB   0       0       10.0.0.1:80         5.6.7.8:11111
ESTAB   0       0       10.0.0.1:22         192.168.1.5:22222
"""

    SS_SYN = """\
State     Recv-Q  Send-Q  Local Address:Port  Peer Address:Port
SYN-RECV  0       0       10.0.0.1:80         9.9.9.9:33333
SYN-RECV  0       0       10.0.0.1:80         9.9.9.9:33334
"""

    async def test_parses_established_connections(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        call_count = 0

        async def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "syn-recv" in cmd:
                return {"stdout": self.SS_SYN, "stderr": "", "returncode": 0, "success": True}
            return {"stdout": self.SS_ESTABLISHED, "stderr": "", "returncode": 0, "success": True}

        pefi.executor.run = mock_run
        result = await pefi._collect_connections()

        ips = {r["ip"] for r in result}
        # 192.168.1.5 adalah private → trusted → diabaikan
        self.assertIn("1.2.3.4", ips)
        self.assertIn("5.6.7.8", ips)
        self.assertNotIn("192.168.1.5", ips)

        ip_data = {r["ip"]: r for r in result}
        # 1.2.3.4 punya 2 koneksi ke port 80 dan 443
        self.assertEqual(ip_data["1.2.3.4"]["conn_count"], 2)
        self.assertIn(80, ip_data["1.2.3.4"]["ports"])
        self.assertIn(443, ip_data["1.2.3.4"]["ports"])

    async def test_syn_flood_counted(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        async def mock_run(cmd, **kwargs):
            if "syn-recv" in cmd:
                return {"stdout": self.SS_SYN, "stderr": "", "returncode": 0, "success": True}
            return {"stdout": "", "stderr": "", "returncode": 0, "success": True}

        pefi.executor.run = mock_run
        result = await pefi._collect_connections()

        ip_data = {r["ip"]: r for r in result}
        self.assertIn("9.9.9.9", ip_data)
        self.assertEqual(ip_data["9.9.9.9"]["conn_syn"], 2)

    async def test_empty_output_returns_empty_list(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.executor.run = _mock_exec("")
        result = await pefi._collect_connections()
        self.assertEqual(result, [])


class TestCollectAuthFailures(unittest.IsolatedAsyncioTestCase):
    """Test _collect_auth_failures() dengan output auth.log yang di-mock."""

    AUTH_LOG = """\
Jun  1 12:00:01 host sshd[1234]: Failed password for root from 1.2.3.4 port 54321 ssh2
Jun  1 12:00:02 host sshd[1234]: Failed password for admin from 1.2.3.4 port 54322 ssh2
Jun  1 12:00:03 host sshd[1235]: Invalid user test from 5.6.7.8 port 11111 ssh2
Jun  1 12:00:04 host sshd[1235]: Failed password for ubuntu from 5.6.7.8 port 11112 ssh2
Jun  1 12:00:05 host sshd[1236]: Accepted publickey for deploy from 192.168.1.10 port 22222 ssh2
"""

    async def test_counts_ssh_failures_per_ip(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.executor.run = _mock_exec(self.AUTH_LOG)

        result = await pefi._collect_auth_failures()
        ip_data = {r["ip"]: r for r in result}

        self.assertEqual(ip_data["1.2.3.4"]["ssh_fail_count"], 2)
        self.assertEqual(ip_data["5.6.7.8"]["ssh_fail_count"], 2)
        # 192.168.1.10 adalah private → tidak masuk hasil
        self.assertNotIn("192.168.1.10", ip_data)

    async def test_no_auth_log_returns_empty(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.executor.run = _mock_exec("")
        result = await pefi._collect_auth_failures()
        self.assertEqual(result, [])


class TestCollectNginxAnomalies(unittest.IsolatedAsyncioTestCase):
    """Test _collect_nginx_anomalies() dengan output access.log yang di-mock."""

    NGINX_LOG = """\
1.2.3.4 - - [01/Jun/2026:12:00:01 +0700] "GET / HTTP/1.1" 200 1234
1.2.3.4 - - [01/Jun/2026:12:00:02 +0700] "GET /wp-admin HTTP/1.1" 404 0
1.2.3.4 - - [01/Jun/2026:12:00:03 +0700] "POST /xmlrpc.php HTTP/1.1" 403 0
5.6.7.8 - - [01/Jun/2026:12:00:04 +0700] "GET /index.html HTTP/1.1" 200 500
10.0.0.5 - - [01/Jun/2026:12:00:05 +0700] "GET /api HTTP/1.1" 500 0
"""

    async def test_counts_requests_and_errors(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.executor.run = _mock_exec(self.NGINX_LOG)

        result = await pefi._collect_nginx_anomalies()
        ip_data = {r["ip"]: r for r in result}

        self.assertEqual(ip_data["1.2.3.4"]["http_req_count"], 3)
        self.assertEqual(ip_data["1.2.3.4"]["http_error_count"], 2)   # 404 + 403
        self.assertEqual(ip_data["5.6.7.8"]["http_req_count"], 1)
        self.assertEqual(ip_data["5.6.7.8"]["http_error_count"], 0)
        # 10.0.0.5 adalah private → tidak masuk
        self.assertNotIn("10.0.0.5", ip_data)


class TestAggregation(unittest.IsolatedAsyncioTestCase):
    """Test _aggregate() menggabungkan semua collector dengan benar."""

    async def test_merge_all_sources(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        conn_stats = [{"ip": "1.2.3.4", "conn_count": 10, "conn_syn": 2, "ports": [80, 443], "port_count": 2}]
        auth_stats = [{"ip": "1.2.3.4", "ssh_fail_count": 5}]
        nginx_stats = [{"ip": "1.2.3.4", "http_req_count": 100, "http_error_count": 20}]

        result = await pefi._aggregate(conn_stats, auth_stats, nginx_stats)
        self.assertEqual(len(result), 1)

        r = result[0]
        self.assertEqual(r["ip"], "1.2.3.4")
        self.assertEqual(r["conn_count"], 10)
        self.assertEqual(r["conn_syn"], 2)
        self.assertEqual(r["ssh_fail_count"], 5)
        self.assertEqual(r["http_req_count"], 100)
        self.assertEqual(r["http_error_count"], 20)
        self.assertIn(80, r["ports_targeted"])
        self.assertIn(443, r["ports_targeted"])

    async def test_different_ips_not_merged(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        conn_stats = [{"ip": "1.1.1.1", "conn_count": 5, "conn_syn": 0, "ports": [80], "port_count": 1}]
        auth_stats = [{"ip": "2.2.2.2", "ssh_fail_count": 3}]

        result = await pefi._aggregate(conn_stats, auth_stats, [])
        ips = {r["ip"] for r in result}
        self.assertIn("1.1.1.1", ips)
        self.assertIn("2.2.2.2", ips)
        self.assertEqual(len(result), 2)

    async def test_empty_collectors_return_empty(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        result = await pefi._aggregate([], [], [])
        self.assertEqual(result, [])


class TestDatabase(unittest.IsolatedAsyncioTestCase):
    """Test DB: _ensure_db, _store_ip_stats, dan management API."""

    def test_ensure_db_creates_all_tables(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        pefi = _make_pefi(db_path)
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        for expected in ["pefi_ip_stats", "pefi_baseline", "pefi_threats",
                         "pefi_rules", "pefi_whitelist"]:
            self.assertIn(expected, tables, f"Tabel {expected} tidak ditemukan")

    def test_store_ip_stats_inserts_rows(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        pefi = _make_pefi(db_path)
        stats = [
            {"ip": "1.2.3.4", "conn_count": 10, "conn_syn": 2,
             "ports_targeted": [80, 443], "port_count": 2,
             "ssh_fail_count": 0, "http_req_count": 50, "http_error_count": 5, "flags": {}},
        ]
        pefi._store_ip_stats(stats)
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT ip, conn_count FROM pefi_ip_stats WHERE ip='1.2.3.4'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 10)

    async def test_whitelist_ip_persists(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        pefi = _make_pefi(db_path)
        msg = await pefi.whitelist_ip("9.9.9.9", "test")
        self.assertIn("whitelist", msg)
        self.assertIn("9.9.9.9", pefi._whitelist_cache)
        # Verifikasi tersimpan di DB
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT ip FROM pefi_whitelist WHERE ip='9.9.9.9'").fetchone()
        conn.close()
        self.assertIsNotNone(row)

    async def test_get_status_returns_string(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        pefi = _make_pefi(db_path)
        status = await pefi.get_status()
        self.assertIsInstance(status, str)
        self.assertIn("PeFi", status)

    async def test_get_active_threats_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        pefi = _make_pefi(db_path)
        result = await pefi.get_active_threats()
        self.assertIn("Tidak ada ancaman", result)

    async def test_get_active_rules_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        pefi = _make_pefi(db_path)
        result = await pefi.get_active_rules()
        self.assertIn("Tidak ada aturan", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
