"""
Sprint 5 — Tests untuk PeFi Hardening & Tuning:
  - _seed_trusted_whitelist()
  - _cleanup_expired_rules()
  - _record_false_positive() + auto-whitelist
  - get_health()
  - Performance: 1000 IP, anomaly detection < 1 detik
"""

import json
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "999")

from modules.pefi import PreEmptiveFirewall, ThreatEvent


def _make_pefi(db_path: str, config: dict = None) -> PreEmptiveFirewall:
    fw = MagicMock()
    fw.deny_ip = AsyncMock(return_value="OK")
    fw.allow_ip = AsyncMock(return_value="OK")
    fw.remove_deny_ip = AsyncMock(return_value="✅ Dihapus")
    notifier = MagicMock()
    notifier.send = AsyncMock()
    pefi = PreEmptiveFirewall(
        executor=MagicMock(), firewall=fw,
        brain=MagicMock(), notifier=notifier,
        db_path=db_path, config=config or {},
    )
    return pefi


def _insert_rule(db_path, ip, active=1, expires_at=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO pefi_rules (ip, rule_type, active, expires_at, reason) VALUES (?,?,?,?,?)",
        (ip, "block", active, expires_at, "test"),
    )
    conn.commit()
    conn.close()


def _insert_fp_threat(db_path, ip, n=1):
    """Insert n false positive threats for an IP."""
    conn = sqlite3.connect(db_path)
    for _ in range(n):
        conn.execute(
            "INSERT INTO pefi_threats (ip, threat_type, severity, action_taken, false_positive) "
            "VALUES (?,?,?,?,1)",
            (ip, "PORT_SCAN", "HIGH", "ignored"),
        )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────
# Seed Trusted Whitelist
# ──────────────────────────────────────────────────────

class TestSeedTrustedWhitelist(unittest.IsolatedAsyncioTestCase):

    async def test_seeds_server_ips_to_whitelist(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        async def mock_run(cmd, **kwargs):
            return {"stdout": "10.0.0.1 192.168.1.5\n", "stderr": "", "returncode": 0, "success": True}

        pefi.executor.run = mock_run
        await pefi._seed_trusted_whitelist()

        self.assertIn("10.0.0.1", pefi._whitelist_cache)
        self.assertIn("192.168.1.5", pefi._whitelist_cache)

        conn = sqlite3.connect(db.name)
        rows = conn.execute("SELECT ip, added_by FROM pefi_whitelist WHERE added_by='system'").fetchall()
        conn.close()
        ips = {r[0] for r in rows}
        self.assertIn("10.0.0.1", ips)
        self.assertIn("192.168.1.5", ips)

    async def test_skips_already_whitelisted_ips(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi._whitelist_cache.add("10.0.0.1")

        async def mock_run(cmd, **kwargs):
            return {"stdout": "10.0.0.1\n", "stderr": "", "returncode": 0, "success": True}

        pefi.executor.run = mock_run
        await pefi._seed_trusted_whitelist()

        conn = sqlite3.connect(db.name)
        count = conn.execute(
            "SELECT COUNT(*) FROM pefi_whitelist WHERE ip='10.0.0.1'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)  # tidak diinsert ulang

    async def test_ignores_invalid_ip_strings(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        async def mock_run(cmd, **kwargs):
            return {"stdout": "not-an-ip garbage 1.2.3.4\n", "stderr": "", "returncode": 0, "success": True}

        pefi.executor.run = mock_run
        await pefi._seed_trusted_whitelist()

        conn = sqlite3.connect(db.name)
        ips = {r[0] for r in conn.execute("SELECT ip FROM pefi_whitelist").fetchall()}
        conn.close()
        self.assertNotIn("not-an-ip", ips)
        self.assertNotIn("garbage", ips)
        self.assertIn("1.2.3.4", ips)

    async def test_handles_empty_output_gracefully(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        async def mock_run(cmd, **kwargs):
            return {"stdout": "", "stderr": "", "returncode": 0, "success": True}

        pefi.executor.run = mock_run
        await pefi._seed_trusted_whitelist()  # tidak crash


# ──────────────────────────────────────────────────────
# Cleanup Expired Rules
# ──────────────────────────────────────────────────────

class TestCleanupExpiredRules(unittest.IsolatedAsyncioTestCase):

    async def test_removes_expired_rule_from_ufw_and_db(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        # Insert rule yang sudah expired (expires_at di masa lalu)
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_rule(db.name, "1.2.3.4", active=1, expires_at=past)

        await pefi._cleanup_expired_rules()

        pefi.firewall.remove_deny_ip.assert_called_once_with("1.2.3.4")
        conn = sqlite3.connect(db.name)
        row = conn.execute("SELECT active FROM pefi_rules WHERE ip='1.2.3.4'").fetchone()
        conn.close()
        self.assertEqual(row[0], 0)  # rule nonaktif

    async def test_does_not_touch_active_future_rules(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        future = (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_rule(db.name, "5.6.7.8", active=1, expires_at=future)

        await pefi._cleanup_expired_rules()

        pefi.firewall.remove_deny_ip.assert_not_called()

    async def test_does_not_touch_permanent_rules(self):
        """Rule tanpa expires_at = permanen, tidak dihapus."""
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        _insert_rule(db.name, "9.9.9.9", active=1, expires_at=None)

        await pefi._cleanup_expired_rules()

        pefi.firewall.remove_deny_ip.assert_not_called()

    async def test_sends_notification_when_rules_cleaned(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_rule(db.name, "2.2.2.2", active=1, expires_at=past)

        await pefi._cleanup_expired_rules()

        pefi.notifier.send.assert_called_once()
        notif = pefi.notifier.send.call_args[0][0]
        self.assertIn("2.2.2.2", notif)

    async def test_continues_if_one_ufw_removal_fails(self):
        """Jika satu UFW removal gagal, rule lain tetap diproses."""
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_rule(db.name, "3.3.3.3", active=1, expires_at=past)
        _insert_rule(db.name, "4.4.4.4", active=1, expires_at=past)

        call_count = 0
        async def flaky_remove(ip):
            nonlocal call_count
            call_count += 1
            if ip == "3.3.3.3":
                raise Exception("UFW error")
            return "OK"

        pefi.firewall.remove_deny_ip = flaky_remove
        await pefi._cleanup_expired_rules()  # tidak crash

        self.assertEqual(call_count, 2)  # tetap coba keduanya

    async def test_no_expired_rules_no_ufw_call(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        await pefi._cleanup_expired_rules()
        pefi.firewall.remove_deny_ip.assert_not_called()


# ──────────────────────────────────────────────────────
# False Positive Feedback Loop
# ──────────────────────────────────────────────────────

class TestFalsePositiveFeedback(unittest.IsolatedAsyncioTestCase):

    async def test_no_auto_whitelist_below_threshold(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {"PEFI_FP_AUTO_WHITELIST_COUNT": "3"})
        _insert_fp_threat(db.name, "1.2.3.4", n=2)  # 2 FP, threshold = 3

        await pefi._record_false_positive("1.2.3.4")

        self.assertNotIn("1.2.3.4", pefi._whitelist_cache)

    async def test_auto_whitelist_at_threshold(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {"PEFI_FP_AUTO_WHITELIST_COUNT": "3"})
        _insert_fp_threat(db.name, "5.6.7.8", n=3)  # 3 FP = threshold

        await pefi._record_false_positive("5.6.7.8")

        self.assertIn("5.6.7.8", pefi._whitelist_cache)

    async def test_auto_whitelist_sends_notification(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {"PEFI_FP_AUTO_WHITELIST_COUNT": "2"})
        _insert_fp_threat(db.name, "7.7.7.7", n=2)

        await pefi._record_false_positive("7.7.7.7")

        pefi.notifier.send.assert_called()
        notif = pefi.notifier.send.call_args[0][0]
        self.assertIn("7.7.7.7", notif)
        self.assertIn("Whitelist", notif)

    async def test_already_trusted_ip_skipped(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {"PEFI_FP_AUTO_WHITELIST_COUNT": "1"})
        pefi._whitelist_cache.add("127.0.0.1")

        await pefi._record_false_positive("127.0.0.1")  # tidak crash, tidak double-whitelist
        pefi.notifier.send.assert_not_called()

    async def test_ignore_threat_triggers_fp_feedback(self):
        """ignore_threat() harus memanggil _record_false_positive()."""
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {"PEFI_FP_AUTO_WHITELIST_COUNT": "5"})

        conn = sqlite3.connect(db.name)
        cur = conn.execute(
            "INSERT INTO pefi_threats (ip, threat_type, severity, action_taken) VALUES (?,?,?,?)",
            ("2.2.2.2", "RECON", "MEDIUM", "pending"),
        )
        tid = cur.lastrowid
        conn.commit()
        conn.close()

        pefi._record_false_positive = AsyncMock()
        await pefi.ignore_threat(tid)
        pefi._record_false_positive.assert_called_once_with("2.2.2.2")


# ──────────────────────────────────────────────────────
# get_health()
# ──────────────────────────────────────────────────────

class TestGetHealth(unittest.IsolatedAsyncioTestCase):

    async def test_returns_string_with_key_sections(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        result = await pefi.get_health()

        self.assertIsInstance(result, str)
        self.assertIn("Health", result)
        self.assertIn("Auto-block", result)
        self.assertIn("Whitelist", result)
        self.assertIn("Baseline", result)

    async def test_reflects_correct_fp_count(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        _insert_fp_threat(db.name, "3.3.3.3", n=2)
        result = await pefi.get_health()
        self.assertIn("2", result)

    async def test_autoblock_status_reflected(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {"PEFI_AUTO_BLOCK": "true"})
        result = await pefi.get_health()
        self.assertIn("ON", result)


# ──────────────────────────────────────────────────────
# Performance Test
# ──────────────────────────────────────────────────────

class TestPerformance(unittest.IsolatedAsyncioTestCase):
    """
    Simulasi 1000 IP aktif — pastikan aggregation dan anomaly detection
    selesai dalam < 1 detik (tanpa I/O nyata).
    """

    def _generate_ip_stats(self, n: int) -> list[dict]:
        stats = []
        for i in range(n):
            a, b = divmod(i, 256)
            ip = f"1.{a}.{b}.1"
            # Setiap 100 IP ada yang anomali
            is_anomaly = (i % 100 == 0)
            stats.append({
                "ip": ip,
                "conn_count": 500 if is_anomaly else 5,
                "conn_syn": 60 if is_anomaly else 0,
                "ports_targeted": list(range(80, 95)) if is_anomaly else [80],
                "port_count": 15 if is_anomaly else 1,
                "ssh_fail_count": 25 if is_anomaly else 0,
                "http_req_count": 100,
                "http_error_count": 80 if is_anomaly else 2,
                "flags": {},
            })
        return stats

    async def test_aggregate_1000_ips_under_1_second(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        conn_stats = self._generate_ip_stats(1000)
        t0 = time.perf_counter()
        result = await pefi._aggregate(conn_stats, [], [])
        elapsed = time.perf_counter() - t0

        self.assertEqual(len(result), 1000)
        self.assertLess(elapsed, 1.0, f"Aggregation terlalu lambat: {elapsed:.2f}s")

    def test_detect_anomalies_1000_ips_under_1_second(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {
            "PEFI_THRESHOLD_CONN_PER_MIN": "200",
            "PEFI_THRESHOLD_PORT_SCAN": "10",
            "PEFI_THRESHOLD_SYN": "50",
            "PEFI_THRESHOLD_SSH_FAIL": "20",
            "PEFI_THRESHOLD_HTTP_ERRORS": "50",
        })
        stats = self._generate_ip_stats(1000)

        t0 = time.perf_counter()
        threats = pefi._detect_anomalies(stats, {})
        elapsed = time.perf_counter() - t0

        # Setiap 100 IP adalah anomali: 1000/100 = 10 anomali IP, masing-masing bisa 5 checks
        self.assertGreater(len(threats), 0)
        self.assertLess(elapsed, 1.0, f"Anomaly detection terlalu lambat: {elapsed:.2f}s")

    def test_baseline_update_1000_samples_performance(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        stats = [{"ip": f"1.0.{i}.1", "conn_count": i % 50, "ports_targeted": [80], "flags": {}}
                 for i in range(100)]

        t0 = time.perf_counter()
        for _ in range(10):  # 10 iterasi baseline update
            pefi._update_baseline(stats)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 2.0, f"Baseline update terlalu lambat: {elapsed:.2f}s")

    def test_store_ip_stats_1000_rows_performance(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        stats = [
            {
                "ip": f"1.{i//256}.{i%256}.1",
                "conn_count": 5, "conn_syn": 0,
                "ports_targeted": [80], "port_count": 1,
                "ssh_fail_count": 0, "http_req_count": 10,
                "http_error_count": 1, "flags": {},
            }
            for i in range(1000)
        ]

        t0 = time.perf_counter()
        pefi._store_ip_stats(stats)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 2.0, f"DB insert 1000 rows terlalu lambat: {elapsed:.2f}s")

        conn = sqlite3.connect(db.name)
        count = conn.execute("SELECT COUNT(*) FROM pefi_ip_stats").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1000)


# ──────────────────────────────────────────────────────
# Telegram: /pefi health subcommand
# ──────────────────────────────────────────────────────

class TestPefiHealthCommand(unittest.IsolatedAsyncioTestCase):

    async def test_health_subcommand_calls_get_health(self):
        from modules.telegram_bot import SyamAdminBot
        from unittest.mock import MagicMock, AsyncMock

        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.get_health = AsyncMock(return_value="🏥 Health OK")

        bot = SyamAdminBot.__new__(SyamAdminBot)
        bot.admin_id = 999
        bot._pending_confirmations = {}
        bot._reply = AsyncMock(return_value=MagicMock())
        bot._edit = AsyncMock()
        bot.modules = {"pefi": pefi}

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 999
        ctx = MagicMock()
        ctx.args = ["health"]

        await bot.cmd_pefi(update, ctx)
        pefi.get_health.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
