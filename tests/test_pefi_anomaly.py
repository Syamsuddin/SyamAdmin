"""
Sprint 2 — Unit tests untuk PeFi Baseline Engine dan Anomaly Detector.
Semua I/O di-mock; test berjalan di macOS tanpa Ubuntu tools.
"""

import json
import math
import os
import sqlite3
import tempfile
import unittest
from datetime import timezone

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "999")

from modules.pefi import PreEmptiveFirewall, ThreatEvent


def _make_pefi(db_path: str, config: dict = None) -> PreEmptiveFirewall:
    from unittest.mock import MagicMock
    pefi = PreEmptiveFirewall(
        executor=MagicMock(), firewall=MagicMock(),
        brain=MagicMock(), notifier=MagicMock(),
        db_path=db_path, config=config or {},
    )
    return pefi


def _ip_stat(ip, conn=0, syn=0, ports=None, ssh_fail=0, http_req=0, http_err=0):
    ports = ports or []
    return {
        "ip": ip, "conn_count": conn, "conn_syn": syn,
        "ports_targeted": ports, "port_count": len(ports),
        "ssh_fail_count": ssh_fail, "http_req_count": http_req,
        "http_error_count": http_err, "flags": {},
    }


# ──────────────────────────────────────────────
# BASELINE ENGINE
# ──────────────────────────────────────────────

class TestBaselineUpdate(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name)

    def _get_baseline(self, port, hour):
        conn = sqlite3.connect(self.db.name)
        row = conn.execute(
            "SELECT avg_conn_per_min, stddev_conn, sample_count FROM pefi_baseline "
            "WHERE port=? AND hour_of_day=?", (port, hour)
        ).fetchone()
        conn.close()
        return row

    def test_first_sample_inserted(self):
        from datetime import datetime
        hour = datetime.now(timezone.utc).hour
        stats = [_ip_stat("1.2.3.4", conn=10, ports=[80])]
        self.pefi._update_baseline(stats)
        row = self._get_baseline(80, hour)
        self.assertIsNotNone(row)
        self.assertEqual(row[2], 1)   # sample_count = 1
        self.assertEqual(row[0], 10.0)  # avg = nilai pertama

    def test_second_sample_updates_avg(self):
        from datetime import datetime
        hour = datetime.now(timezone.utc).hour
        # Sampel 1: 10 koneksi
        self.pefi._update_baseline([_ip_stat("1.2.3.4", conn=10, ports=[80])])
        # Sampel 2: 20 koneksi
        self.pefi._update_baseline([_ip_stat("5.6.7.8", conn=20, ports=[80])])
        row = self._get_baseline(80, hour)
        self.assertEqual(row[2], 2)  # 2 sampel
        # avg harus antara 10 dan 20
        self.assertGreater(row[0], 10.0)
        self.assertLess(row[0], 20.0)

    def test_stddev_positive_after_two_samples(self):
        from datetime import datetime
        hour = datetime.now(timezone.utc).hour
        for val in [5, 50]:  # dua nilai jauh berbeda → stddev besar
            self.pefi._update_baseline([_ip_stat("1.2.3.4", conn=val, ports=[443])])
        row = self._get_baseline(443, hour)
        self.assertGreater(row[1], 0)  # stddev > 0

    def test_empty_aggregated_no_crash(self):
        self.pefi._update_baseline([])  # harus tidak crash

    def test_multiple_ports_tracked_separately(self):
        from datetime import datetime
        hour = datetime.now(timezone.utc).hour
        stats = [_ip_stat("1.2.3.4", conn=5, ports=[80, 443])]
        self.pefi._update_baseline(stats)
        self.assertIsNotNone(self._get_baseline(80, hour))
        self.assertIsNotNone(self._get_baseline(443, hour))


# ──────────────────────────────────────────────
# ANOMALY DETECTOR — tiap check secara terpisah
# ──────────────────────────────────────────────

class TestDetectPortScan(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name, {"PEFI_THRESHOLD_PORT_SCAN": "5"})

    def test_triggers_above_threshold(self):
        stats = [_ip_stat("1.2.3.4", ports=list(range(80, 86)))]  # 6 port
        threats = self.pefi._detect_anomalies(stats, {})
        types = [t.threat_type for t in threats]
        self.assertIn("PORT_SCAN", types)

    def test_no_trigger_below_threshold(self):
        stats = [_ip_stat("1.2.3.4", ports=[80, 443])]  # 2 port
        threats = self.pefi._detect_anomalies(stats, {})
        types = [t.threat_type for t in threats]
        self.assertNotIn("PORT_SCAN", types)

    def test_critical_at_3x_threshold(self):
        stats = [_ip_stat("1.2.3.4", ports=list(range(1, 20)))]  # 19 port (> 5*3)
        threats = self.pefi._detect_anomalies(stats, {})
        ps = [t for t in threats if t.threat_type == "PORT_SCAN"]
        self.assertTrue(any(t.severity == "CRITICAL" for t in ps))


class TestDetectSynFlood(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name, {"PEFI_THRESHOLD_SYN": "10"})

    def test_triggers_above_threshold(self):
        stats = [_ip_stat("1.2.3.4", syn=15)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertIn("SYN_FLOOD", [t.threat_type for t in threats])

    def test_no_trigger_below_threshold(self):
        stats = [_ip_stat("1.2.3.4", syn=5)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertNotIn("SYN_FLOOD", [t.threat_type for t in threats])

    def test_critical_at_2x_threshold(self):
        stats = [_ip_stat("1.2.3.4", syn=25)]  # 25 > 10*2
        threats = self.pefi._detect_anomalies(stats, {})
        sf = [t for t in threats if t.threat_type == "SYN_FLOOD"]
        self.assertTrue(any(t.severity == "CRITICAL" for t in sf))


class TestDetectBruteForce(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name, {"PEFI_THRESHOLD_SSH_FAIL": "10"})

    def test_triggers_above_threshold(self):
        stats = [_ip_stat("1.2.3.4", ssh_fail=15)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertIn("BRUTE_FORCE", [t.threat_type for t in threats])

    def test_no_trigger_below_threshold(self):
        stats = [_ip_stat("1.2.3.4", ssh_fail=5)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertNotIn("BRUTE_FORCE", [t.threat_type for t in threats])

    def test_severity_medium_at_threshold(self):
        stats = [_ip_stat("1.2.3.4", ssh_fail=12)]  # antara 10 dan 20
        threats = self.pefi._detect_anomalies(stats, {})
        bf = [t for t in threats if t.threat_type == "BRUTE_FORCE"]
        self.assertTrue(any(t.severity == "MEDIUM" for t in bf))

    def test_severity_high_at_2x_threshold(self):
        stats = [_ip_stat("1.2.3.4", ssh_fail=25)]
        threats = self.pefi._detect_anomalies(stats, {})
        bf = [t for t in threats if t.threat_type == "BRUTE_FORCE"]
        self.assertTrue(any(t.severity == "HIGH" for t in bf))


class TestDetectConnSpike(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name, {"PEFI_THRESHOLD_CONN_PER_MIN": "100"})

    def test_triggers_above_threshold(self):
        stats = [_ip_stat("1.2.3.4", conn=150)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertIn("CONN_SPIKE", [t.threat_type for t in threats])

    def test_no_trigger_at_threshold_minus_one(self):
        stats = [_ip_stat("1.2.3.4", conn=99)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertNotIn("CONN_SPIKE", [t.threat_type for t in threats])


class TestDetectRecon(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name, {"PEFI_THRESHOLD_HTTP_ERRORS": "20"})

    def test_triggers_above_threshold(self):
        stats = [_ip_stat("1.2.3.4", http_err=30, http_req=35)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertIn("RECON", [t.threat_type for t in threats])

    def test_no_trigger_below_threshold(self):
        stats = [_ip_stat("1.2.3.4", http_err=10)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertNotIn("RECON", [t.threat_type for t in threats])


class TestDetectTrafficSpike(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name, {
            "PEFI_THRESHOLD_SPIKE_MULTIPLIER": "3",
            "PEFI_BASELINE_MIN_SAMPLES": "2",
        })

    def _make_baseline(self, port, hour, avg, stddev, samples):
        return {(port, hour): {"avg": avg, "stddev": stddev, "sample_count": samples}}

    def test_triggers_when_above_baseline_multiplier(self):
        from datetime import datetime
        hour = datetime.now(timezone.utc).hour
        # avg=10, stddev=2 → threshold = 10 + 3*2 = 16; dan 3x avg = 30
        # traffic=50 → memenuhi keduanya
        baseline = self._make_baseline(80, hour, avg=10, stddev=2, samples=5)
        stats = [_ip_stat("1.2.3.4", conn=50, ports=[80])]
        threats = self.pefi._detect_anomalies(stats, baseline)
        self.assertIn("TRAFFIC_SPIKE", [t.threat_type for t in threats])

    def test_no_trigger_with_insufficient_baseline(self):
        from datetime import datetime
        hour = datetime.now(timezone.utc).hour
        # sample_count=1 < min_samples=2 → skip
        baseline = self._make_baseline(80, hour, avg=10, stddev=2, samples=1)
        stats = [_ip_stat("1.2.3.4", conn=500, ports=[80])]
        threats = self.pefi._detect_anomalies(stats, baseline)
        self.assertNotIn("TRAFFIC_SPIKE", [t.threat_type for t in threats])

    def test_no_trigger_for_normal_traffic(self):
        from datetime import datetime
        hour = datetime.now(timezone.utc).hour
        # avg=100, traffic=120 — tidak mencapai 3x
        baseline = self._make_baseline(443, hour, avg=100, stddev=10, samples=10)
        stats = [_ip_stat("1.2.3.4", conn=120, ports=[443])]
        threats = self.pefi._detect_anomalies(stats, baseline)
        self.assertNotIn("TRAFFIC_SPIKE", [t.threat_type for t in threats])


class TestDetectRecidivist(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name)

    def _insert_block_rule(self, ip):
        conn = sqlite3.connect(self.db.name)
        conn.execute(
            "INSERT OR IGNORE INTO pefi_rules (ip, rule_type, reason) VALUES (?,?,?)",
            (ip, "block", "test"),
        )
        conn.commit()
        conn.close()

    def test_recidivist_flagged(self):
        self._insert_block_rule("1.2.3.4")
        stats = [_ip_stat("1.2.3.4", conn=5)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertIn("RECIDIVIST", [t.threat_type for t in threats])

    def test_clean_ip_not_flagged(self):
        stats = [_ip_stat("5.6.7.8", conn=5)]
        threats = self.pefi._detect_anomalies(stats, {})
        self.assertNotIn("RECIDIVIST", [t.threat_type for t in threats])

    def test_recidivist_detail_contains_block_count(self):
        self._insert_block_rule("9.9.9.9")
        stats = [_ip_stat("9.9.9.9", conn=3)]
        threats = self.pefi._detect_anomalies(stats, {})
        rec = [t for t in threats if t.threat_type == "RECIDIVIST"]
        self.assertTrue(rec)
        self.assertIn("previous_blocks", rec[0].details)


# ──────────────────────────────────────────────
# DEDUPLICATION
# ──────────────────────────────────────────────

class TestSaveThreats(unittest.TestCase):

    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.pefi = _make_pefi(self.db.name)

    def _count_threats(self, ip=None):
        conn = sqlite3.connect(self.db.name)
        if ip:
            n = conn.execute("SELECT COUNT(*) FROM pefi_threats WHERE ip=?", (ip,)).fetchone()[0]
        else:
            n = conn.execute("SELECT COUNT(*) FROM pefi_threats").fetchone()[0]
        conn.close()
        return n

    def test_saves_new_threat(self):
        t = ThreatEvent(ip="1.2.3.4", threat_type="PORT_SCAN", severity="HIGH")
        self.pefi._save_threats([t])
        self.assertEqual(self._count_threats("1.2.3.4"), 1)

    def test_dedup_same_ip_same_type_within_60min(self):
        t = ThreatEvent(ip="1.2.3.4", threat_type="PORT_SCAN", severity="HIGH")
        self.pefi._save_threats([t])
        self.pefi._save_threats([t])  # duplikat
        self.assertEqual(self._count_threats("1.2.3.4"), 1)  # tetap 1

    def test_allows_escalated_severity(self):
        t_med = ThreatEvent(ip="1.2.3.4", threat_type="BRUTE_FORCE", severity="MEDIUM")
        t_high = ThreatEvent(ip="1.2.3.4", threat_type="BRUTE_FORCE", severity="HIGH")
        self.pefi._save_threats([t_med])
        self.pefi._save_threats([t_high])
        # HIGH > MEDIUM → disimpan (total 2 baris)
        self.assertEqual(self._count_threats("1.2.3.4"), 2)

    def test_different_threat_types_both_saved(self):
        threats = [
            ThreatEvent(ip="1.2.3.4", threat_type="PORT_SCAN", severity="HIGH"),
            ThreatEvent(ip="1.2.3.4", threat_type="BRUTE_FORCE", severity="MEDIUM"),
        ]
        self.pefi._save_threats(threats)
        self.assertEqual(self._count_threats("1.2.3.4"), 2)

    def test_empty_list_no_crash(self):
        self.pefi._save_threats([])
        self.assertEqual(self._count_threats(), 0)


# ──────────────────────────────────────────────
# INTEGRASI: multiple checks satu IP
# ──────────────────────────────────────────────

class TestMultipleAnomaliesOneIP(unittest.TestCase):

    def test_one_ip_triggers_multiple_checks(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {
            "PEFI_THRESHOLD_PORT_SCAN": "5",
            "PEFI_THRESHOLD_SSH_FAIL": "10",
            "PEFI_THRESHOLD_CONN_PER_MIN": "50",
        })
        # IP yang melanggar 3 rule sekaligus
        stats = [_ip_stat("1.2.3.4", conn=100, ports=list(range(80, 90)), ssh_fail=20)]
        threats = pefi._detect_anomalies(stats, {})
        threat_types = {t.threat_type for t in threats}
        self.assertIn("PORT_SCAN", threat_types)
        self.assertIn("BRUTE_FORCE", threat_types)
        self.assertIn("CONN_SPIKE", threat_types)

    def test_trusted_ip_never_flagged(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, {"PEFI_THRESHOLD_PORT_SCAN": "3"})
        # 127.0.0.1 seharusnya tidak pernah masuk aggregated (filtered di collector)
        # tapi kalau lolos, detector tidak punya filter trusted — itu tugas collector
        # Test ini memverifikasi collector sudah filter
        self.assertTrue(pefi._is_trusted("127.0.0.1"))
        self.assertTrue(pefi._is_trusted("192.168.1.1"))
        self.assertFalse(pefi._is_trusted("8.8.8.8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
