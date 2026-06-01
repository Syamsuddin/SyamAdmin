"""
Sprint 3 — Unit tests untuk PeFi AI Analysis Engine dan Decision Engine.
AIBrain di-mock agar test tidak butuh API key Anthropic.
"""

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "999")

from modules.pefi import PreEmptiveFirewall, ThreatEvent


def _make_pefi(db_path: str, config: dict = None, auto_block: bool = False) -> PreEmptiveFirewall:
    cfg = config or {}
    if auto_block:
        cfg["PEFI_AUTO_BLOCK"] = "true"
        cfg["PEFI_AUTO_BLOCK_CONFIDENCE"] = "0.90"
    brain = MagicMock()
    brain.enabled = True
    firewall = MagicMock()
    firewall.deny_ip = AsyncMock(return_value="✅ IP diblokir")
    firewall.allow_ip = AsyncMock(return_value="✅ IP diizinkan")
    notifier = MagicMock()
    notifier.send = AsyncMock()
    pefi = PreEmptiveFirewall(
        executor=MagicMock(), firewall=firewall,
        brain=brain, notifier=notifier,
        db_path=db_path, config=cfg,
    )
    return pefi


def _insert_threat(db_path, ip="1.2.3.4", ttype="PORT_SCAN",
                   severity="HIGH", action="pending", details=None):
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO pefi_threats (ip, threat_type, severity, action_taken, details) "
        "VALUES (?,?,?,?,?)",
        (ip, ttype, severity, action, json.dumps(details or {})),
    )
    threat_id = cur.lastrowid
    conn.commit()
    conn.close()
    return threat_id


# ──────────────────────────────────────────────────────
# PEFI_ANALYSIS_TOOL schema validation
# ──────────────────────────────────────────────────────

class TestPefiAnalysisTool(unittest.TestCase):

    def test_tool_schema_has_required_fields(self):
        from modules.brain import PEFI_ANALYSIS_TOOL
        schema = PEFI_ANALYSIS_TOOL["input_schema"]
        self.assertIn("decisions", schema["properties"])
        self.assertIn("summary", schema["properties"])
        self.assertIn("decisions", schema["required"])

    def test_decision_item_has_required_fields(self):
        from modules.brain import PEFI_ANALYSIS_TOOL
        item = PEFI_ANALYSIS_TOOL["input_schema"]["properties"]["decisions"]["items"]
        required = item["required"]
        for field in ["threat_id", "ip", "verdict", "confidence", "reason"]:
            self.assertIn(field, required)

    def test_verdict_enum_values(self):
        from modules.brain import PEFI_ANALYSIS_TOOL
        item = PEFI_ANALYSIS_TOOL["input_schema"]["properties"]["decisions"]["items"]
        verdicts = item["properties"]["verdict"]["enum"]
        for v in ["BLOCK", "THROTTLE", "MONITOR", "IGNORE"]:
            self.assertIn(v, verdicts)


# ──────────────────────────────────────────────────────
# _analyze_with_ai() — AI fallback ketika brain nonaktif
# ──────────────────────────────────────────────────────

class TestAnalyzeWithAiFallback(unittest.IsolatedAsyncioTestCase):

    async def test_returns_monitor_when_brain_disabled(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.brain.enabled = False  # nonaktifkan AI

        pending = [
            {"id": 1, "ip": "1.2.3.4", "threat_type": "PORT_SCAN",
             "severity": "HIGH", "details": {}},
        ]
        decisions = await pefi._analyze_with_ai(pending)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["verdict"], "MONITOR")
        self.assertEqual(decisions[0]["ip"], "1.2.3.4")

    async def test_returns_empty_for_empty_pending(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        decisions = await pefi._analyze_with_ai([])
        self.assertEqual(decisions, [])

    async def test_calls_brain_when_enabled(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.brain.analyze_pefi_threats = AsyncMock(return_value=[
            {"threat_id": 1, "ip": "1.2.3.4", "verdict": "BLOCK",
             "confidence": 0.95, "reason": "Port scan masif", "block_duration_hours": 24}
        ])
        pending = [{"id": 1, "ip": "1.2.3.4", "threat_type": "PORT_SCAN",
                    "severity": "HIGH", "details": {}}]
        decisions = await pefi._analyze_with_ai(pending)
        pefi.brain.analyze_pefi_threats.assert_called_once()
        self.assertEqual(decisions[0]["verdict"], "BLOCK")


# ──────────────────────────────────────────────────────
# _apply_decisions() — Decision Engine 4 Tier
# ──────────────────────────────────────────────────────

class TestApplyDecisions(unittest.IsolatedAsyncioTestCase):

    async def test_tier0_ignore_marks_as_ignored(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        tid = _insert_threat(db.name, "1.2.3.4")

        await pefi._apply_decisions([{
            "threat_id": tid, "ip": "1.2.3.4", "verdict": "IGNORE",
            "confidence": 0.3, "reason": "false positive", "block_duration_hours": 0
        }])

        conn = sqlite3.connect(db.name)
        row = conn.execute("SELECT action_taken FROM pefi_threats WHERE id=?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row[0], "ignored")

    async def test_tier3_monitor_marks_as_monitoring(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        tid = _insert_threat(db.name, "2.2.2.2")

        await pefi._apply_decisions([{
            "threat_id": tid, "ip": "2.2.2.2", "verdict": "MONITOR",
            "confidence": 0.6, "reason": "pantau dulu", "block_duration_hours": 0
        }])

        conn = sqlite3.connect(db.name)
        row = conn.execute("SELECT action_taken FROM pefi_threats WHERE id=?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row[0], "monitoring")

    async def test_tier3_throttle_treated_as_monitor(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        tid = _insert_threat(db.name, "3.3.3.3")

        await pefi._apply_decisions([{
            "threat_id": tid, "ip": "3.3.3.3", "verdict": "THROTTLE",
            "confidence": 0.65, "reason": "rate limit", "block_duration_hours": 0
        }])

        conn = sqlite3.connect(db.name)
        row = conn.execute("SELECT action_taken FROM pefi_threats WHERE id=?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row[0], "monitoring")

    async def test_tier1_autoblock_executes_when_enabled(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, auto_block=True)
        tid = _insert_threat(db.name, "4.4.4.4", severity="HIGH")

        await pefi._apply_decisions([{
            "threat_id": tid, "ip": "4.4.4.4", "verdict": "BLOCK",
            "confidence": 0.97,  # >= 0.90 threshold
            "reason": "Port scan masif dari CN",
            "block_duration_hours": 24
        }])

        # Pastikan UFW deny_ip dipanggil
        pefi.firewall.deny_ip.assert_called_once()
        # Pastikan notif terkirim
        pefi.notifier.send.assert_called_once()
        # Pastikan status DB terupdate
        conn = sqlite3.connect(db.name)
        row = conn.execute("SELECT action_taken FROM pefi_threats WHERE id=?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row[0], "blocked")

    async def test_tier1_autoblock_skipped_when_disabled(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, auto_block=False)  # auto_block OFF
        tid = _insert_threat(db.name, "5.5.5.5", severity="HIGH")

        await pefi._apply_decisions([{
            "threat_id": tid, "ip": "5.5.5.5", "verdict": "BLOCK",
            "confidence": 0.99, "reason": "SYN flood", "block_duration_hours": 6
        }])

        # UFW TIDAK dipanggil
        pefi.firewall.deny_ip.assert_not_called()
        # Status harus awaiting_confirm
        conn = sqlite3.connect(db.name)
        row = conn.execute("SELECT action_taken FROM pefi_threats WHERE id=?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row[0], "awaiting_confirm")

    async def test_tier2_block_low_confidence_sends_notification(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name, auto_block=True)
        tid = _insert_threat(db.name, "6.6.6.6")

        await pefi._apply_decisions([{
            "threat_id": tid, "ip": "6.6.6.6", "verdict": "BLOCK",
            "confidence": 0.75,  # < 0.90 threshold → Tier 2
            "reason": "Brute force SSH", "block_duration_hours": 12
        }])

        # UFW tidak dipanggil (confidence kurang)
        pefi.firewall.deny_ip.assert_not_called()
        # Notif konfirmasi dikirim
        pefi.notifier.send.assert_called_once()
        notif_text = pefi.notifier.send.call_args[0][0]
        self.assertIn("Konfirmasi Blokir", notif_text)
        self.assertIn("6.6.6.6", notif_text)

    async def test_missing_threat_id_skipped(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        # Tidak ada crash meskipun threat_id kosong
        await pefi._apply_decisions([{
            "threat_id": None, "ip": "", "verdict": "BLOCK",
            "confidence": 0.99, "reason": "test"
        }])
        pefi.firewall.deny_ip.assert_not_called()


# ──────────────────────────────────────────────────────
# _update_threat_status()
# ──────────────────────────────────────────────────────

class TestUpdateThreatStatus(unittest.TestCase):

    def test_updates_all_fields(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        tid = _insert_threat(db.name, "7.7.7.7")

        pefi._update_threat_status(tid, "BLOCK", 0.92, "Port scan besar", "blocked")

        conn = sqlite3.connect(db.name)
        row = conn.execute(
            "SELECT ai_verdict, confidence, ai_reason, action_taken FROM pefi_threats WHERE id=?",
            (tid,)
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "BLOCK")
        self.assertAlmostEqual(row[1], 0.92, places=2)
        self.assertEqual(row[2], "Port scan besar")
        self.assertEqual(row[3], "blocked")


# ──────────────────────────────────────────────────────
# approve_block() dan ignore_threat()
# ──────────────────────────────────────────────────────

class TestManagementActions(unittest.IsolatedAsyncioTestCase):

    async def test_approve_block_executes_ufw(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        _insert_threat(db.name, "8.8.8.8", action="awaiting_confirm")

        result = await pefi.approve_block("8.8.8.8", duration_hours=12)
        pefi.firewall.deny_ip.assert_called_once()
        self.assertIn("berhasil diblokir", result)

    async def test_approve_block_no_pending_returns_info(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)

        result = await pefi.approve_block("9.9.9.9")
        pefi.firewall.deny_ip.assert_not_called()
        self.assertIn("Tidak ada ancaman pending", result)

    async def test_ignore_threat_marks_false_positive(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        tid = _insert_threat(db.name, "1.1.1.1", action="awaiting_confirm")

        result = await pefi.ignore_threat(tid)
        self.assertIn("false positive", result)

        conn = sqlite3.connect(db.name)
        row = conn.execute(
            "SELECT action_taken, false_positive FROM pefi_threats WHERE id=?", (tid,)
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "ignored")
        self.assertEqual(row[1], 1)

    async def test_get_report_empty(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        result = await pefi.get_report(hours=24)
        self.assertIn("Tidak ada aktivitas", result)

    async def test_get_report_with_threats(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        _insert_threat(db.name, "2.2.2.2", ttype="PORT_SCAN", severity="HIGH", action="blocked")
        _insert_threat(db.name, "3.3.3.3", ttype="BRUTE_FORCE", severity="MEDIUM", action="monitoring")

        result = await pefi.get_report(hours=24)
        self.assertIn("PORT_SCAN", result)
        self.assertIn("BRUTE_FORCE", result)


# ──────────────────────────────────────────────────────
# AIBrain.analyze_pefi_threats() — unit test dengan mock Anthropic client
# ──────────────────────────────────────────────────────

class TestBrainAnalyzePefiThreats(unittest.IsolatedAsyncioTestCase):

    async def test_returns_fallback_when_disabled(self):
        from modules.brain import AIBrain
        brain = AIBrain(api_key="", db_path=":memory:")
        threats = [{"id": 1, "ip": "1.2.3.4", "threat_type": "PORT_SCAN",
                    "severity": "HIGH", "details": {}}]
        result = await brain.analyze_pefi_threats(threats)
        self.assertEqual(result, [])  # disabled → return []

    async def test_returns_empty_for_empty_threats(self):
        from modules.brain import AIBrain
        brain = AIBrain(api_key="sk-test", db_path=":memory:")
        result = await brain.analyze_pefi_threats([])
        self.assertEqual(result, [])

    async def test_calls_claude_with_tool_use(self):
        from modules.brain import AIBrain, PEFI_ANALYSIS_TOOL
        brain = AIBrain(api_key="sk-test", db_path=":memory:")

        # Mock Anthropic client
        mock_response = MagicMock()
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.input = {
            "decisions": [
                {"threat_id": 1, "ip": "1.2.3.4", "verdict": "BLOCK",
                 "confidence": 0.95, "reason": "Port scan masif"}
            ],
            "summary": "Ditemukan 1 ancaman serius"
        }
        mock_response.content = [mock_block]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        brain._client = mock_client

        threats = [{"id": 1, "ip": "1.2.3.4", "threat_type": "PORT_SCAN",
                    "severity": "HIGH", "details": {"port_count": 15}}]
        result = await brain.analyze_pefi_threats(threats, "Nginx, MySQL aktif")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["verdict"], "BLOCK")
        self.assertEqual(result[0]["ip"], "1.2.3.4")
        # Verifikasi PEFI_ANALYSIS_TOOL dipakai
        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertIn(PEFI_ANALYSIS_TOOL, call_kwargs.get("tools", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
