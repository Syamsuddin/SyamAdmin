"""
Sprint 4 — Unit tests untuk cmd_pefi Telegram handler.
Telegram Update/Context di-mock; tidak butuh bot token nyata.
"""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "999")

from modules.pefi import PreEmptiveFirewall


# ── Helpers ──────────────────────────────────────────────────────────────

ADMIN_ID = 999


def _make_update(text_or_args=None, user_id=ADMIN_ID):
    """Buat mock Telegram Update dengan user yang bisa dikonfigurasi."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.message = MagicMock()
    update.message.text = text_or_args or ""
    return update


def _make_context(args=None):
    """Buat mock Telegram Context dengan args."""
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


def _make_pefi(db_path: str) -> PreEmptiveFirewall:
    pefi = PreEmptiveFirewall(
        executor=MagicMock(),
        firewall=MagicMock(),
        brain=MagicMock(),
        notifier=MagicMock(),
        db_path=db_path,
        config={"PEFI_ENABLED": "true", "PEFI_AUTO_BLOCK": "false"},
    )
    pefi.firewall.deny_ip = AsyncMock(return_value="OK")
    pefi.firewall.allow_ip = AsyncMock(return_value="OK")
    return pefi


def _make_bot(pefi=None, db_path=None):
    """Buat minimal SyamAdminBot instance dengan modules yang relevan."""
    from modules.telegram_bot import SyamAdminBot
    bot = SyamAdminBot.__new__(SyamAdminBot)
    bot.token = "123:test"
    bot.admin_id = ADMIN_ID
    bot.server_name = "test-vps"
    bot._pending_confirmations = {}
    bot._wizard_states = {}
    bot._plan_running = False
    bot._public_ip_cache = ("", 0.0)

    _pefi = pefi or (_make_pefi(db_path) if db_path else _make_pefi(tempfile.mktemp(suffix=".db")))
    bot.modules = {
        "pefi": _pefi,
        "brain": MagicMock(),
        "firewall": MagicMock(),
        "executor": MagicMock(),
        "notifier": MagicMock(),
    }
    # Patch _reply dan _edit agar tidak perlu koneksi Telegram
    bot._reply = AsyncMock(return_value=MagicMock())
    bot._edit = AsyncMock()
    bot._generate_otp = lambda: "1234"
    return bot, _pefi


# ── Tests: info subcommands (tanpa OTP) ──────────────────────────────────

class TestPefiInfoCommands(unittest.IsolatedAsyncioTestCase):

    async def test_no_args_calls_get_status(self):
        bot, pefi = _make_bot()
        pefi.get_status = AsyncMock(return_value="✅ Status OK")
        await bot.cmd_pefi(_make_update(), _make_context([]))
        pefi.get_status.assert_called_once()

    async def test_status_subcommand(self):
        bot, pefi = _make_bot()
        pefi.get_status = AsyncMock(return_value="🛡️ Status")
        await bot.cmd_pefi(_make_update(), _make_context(["status"]))
        pefi.get_status.assert_called_once()

    async def test_threats_subcommand(self):
        bot, pefi = _make_bot()
        pefi.get_active_threats = AsyncMock(return_value="⚠️ Threats")
        await bot.cmd_pefi(_make_update(), _make_context(["threats"]))
        pefi.get_active_threats.assert_called_once()

    async def test_rules_subcommand(self):
        bot, pefi = _make_bot()
        pefi.get_active_rules = AsyncMock(return_value="🔒 Rules")
        await bot.cmd_pefi(_make_update(), _make_context(["rules"]))
        pefi.get_active_rules.assert_called_once()

    async def test_report_default_24h(self):
        bot, pefi = _make_bot()
        pefi.get_report = AsyncMock(return_value="📊 Report")
        await bot.cmd_pefi(_make_update(), _make_context(["report"]))
        pefi.get_report.assert_called_once_with(hours=24)

    async def test_report_custom_hours(self):
        bot, pefi = _make_bot()
        pefi.get_report = AsyncMock(return_value="📊 Report")
        await bot.cmd_pefi(_make_update(), _make_context(["report", "48"]))
        pefi.get_report.assert_called_once_with(hours=48)

    async def test_unknown_subcommand_sends_help(self):
        bot, pefi = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["xyz"]))
        # _reply dipanggil dengan pesan bantuan
        call_args = bot._reply.call_args[0][1]
        self.assertIn("Sub-command tidak dikenal", call_args)

    async def test_pefi_module_absent_returns_error(self):
        bot, _ = _make_bot()
        bot.modules["pefi"] = None
        await bot.cmd_pefi(_make_update(), _make_context([]))
        call_args = bot._reply.call_args[0][1]
        self.assertIn("tidak aktif", call_args)


# ── Tests: OTP-gated subcommands ─────────────────────────────────────────

class TestPefiOtpCommands(unittest.IsolatedAsyncioTestCase):

    async def test_scan_stores_pending_otp(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["scan"]))
        self.assertIn(ADMIN_ID, bot._pending_confirmations)
        self.assertEqual(bot._pending_confirmations[ADMIN_ID]["action"], "pefi_scan")
        self.assertEqual(bot._pending_confirmations[ADMIN_ID]["otp"], "1234")

    async def test_block_stores_pending_with_ip(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["block", "1.2.3.4", "6"]))
        pending = bot._pending_confirmations[ADMIN_ID]
        self.assertEqual(pending["action"], "pefi_block")
        self.assertEqual(pending["ip"], "1.2.3.4")
        self.assertEqual(pending["hours"], 6)

    async def test_block_without_ip_shows_error(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["block"]))
        self.assertNotIn(ADMIN_ID, bot._pending_confirmations)

    async def test_unblock_stores_pending_with_ip(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["unblock", "5.6.7.8"]))
        pending = bot._pending_confirmations[ADMIN_ID]
        self.assertEqual(pending["action"], "pefi_unblock")
        self.assertEqual(pending["ip"], "5.6.7.8")

    async def test_whitelist_stores_pending_with_reason(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["whitelist", "9.9.9.9", "trusted", "cdn"]))
        pending = bot._pending_confirmations[ADMIN_ID]
        self.assertEqual(pending["action"], "pefi_whitelist")
        self.assertEqual(pending["ip"], "9.9.9.9")
        self.assertIn("trusted", pending["reason"])

    async def test_ignore_stores_pending_with_threat_id(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["ignore", "42"]))
        pending = bot._pending_confirmations[ADMIN_ID]
        self.assertEqual(pending["action"], "pefi_ignore")
        self.assertEqual(pending["threat_id"], 42)

    async def test_ignore_without_id_shows_error(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["ignore"]))
        self.assertNotIn(ADMIN_ID, bot._pending_confirmations)

    async def test_autoblock_on_stores_pending(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["autoblock", "on"]))
        pending = bot._pending_confirmations[ADMIN_ID]
        self.assertEqual(pending["action"], "pefi_autoblock")
        self.assertEqual(pending["toggle"], "on")

    async def test_autoblock_off_stores_pending(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["autoblock", "off"]))
        pending = bot._pending_confirmations[ADMIN_ID]
        self.assertEqual(pending["toggle"], "off")

    async def test_autoblock_no_arg_shows_status(self):
        bot, _ = _make_bot()
        await bot.cmd_pefi(_make_update(), _make_context(["autoblock"]))
        self.assertNotIn(ADMIN_ID, bot._pending_confirmations)
        call_text = bot._reply.call_args[0][1]
        self.assertIn("Auto-Block", call_text)


# ── Tests: _execute_confirmed_action PeFi handlers ───────────────────────

class TestExecuteConfirmedPefiActions(unittest.IsolatedAsyncioTestCase):

    async def test_pefi_scan_executes(self):
        bot, pefi = _make_bot()
        pefi.scan_now = AsyncMock(return_value="✅ Scan selesai")
        pending = {"action": "pefi_scan", "otp": "1234",
                   "expires": datetime.now().timestamp() + 60}
        await bot._execute_confirmed_action(_make_update(), pending)
        pefi.scan_now.assert_called_once()

    async def test_pefi_block_calls_approve_block(self):
        bot, pefi = _make_bot()
        pefi.approve_block = AsyncMock(return_value="✅ Diblokir")
        pending = {"action": "pefi_block", "ip": "1.2.3.4", "hours": 12,
                   "otp": "1234", "expires": datetime.now().timestamp() + 60}
        await bot._execute_confirmed_action(_make_update(), pending)
        pefi.approve_block.assert_called_once_with("1.2.3.4", duration_hours=12)

    async def test_pefi_unblock_calls_remove_rule(self):
        bot, pefi = _make_bot()
        pefi.remove_rule = AsyncMock(return_value="✅ Blokir dihapus")
        pending = {"action": "pefi_unblock", "ip": "5.6.7.8",
                   "otp": "1234", "expires": datetime.now().timestamp() + 60}
        await bot._execute_confirmed_action(_make_update(), pending)
        pefi.remove_rule.assert_called_once_with("5.6.7.8")

    async def test_pefi_whitelist_calls_whitelist_ip(self):
        bot, pefi = _make_bot()
        pefi.whitelist_ip = AsyncMock(return_value="✅ Di-whitelist")
        pending = {"action": "pefi_whitelist", "ip": "9.9.9.9",
                   "reason": "CDN trusted", "otp": "1234",
                   "expires": datetime.now().timestamp() + 60}
        await bot._execute_confirmed_action(_make_update(), pending)
        pefi.whitelist_ip.assert_called_once_with("9.9.9.9", reason="CDN trusted")

    async def test_pefi_ignore_calls_ignore_threat(self):
        bot, pefi = _make_bot()
        pefi.ignore_threat = AsyncMock(return_value="✅ Diabaikan")
        pending = {"action": "pefi_ignore", "threat_id": 7,
                   "otp": "1234", "expires": datetime.now().timestamp() + 60}
        await bot._execute_confirmed_action(_make_update(), pending)
        pefi.ignore_threat.assert_called_once_with(7)

    async def test_pefi_autoblock_on_sets_config(self):
        bot, pefi = _make_bot()
        pending = {"action": "pefi_autoblock", "toggle": "on",
                   "otp": "1234", "expires": datetime.now().timestamp() + 60}
        await bot._execute_confirmed_action(_make_update(), pending)
        self.assertEqual(pefi.config["PEFI_AUTO_BLOCK"], "true")

    async def test_pefi_autoblock_off_sets_config(self):
        bot, pefi = _make_bot()
        pefi.config["PEFI_AUTO_BLOCK"] = "true"
        pending = {"action": "pefi_autoblock", "toggle": "off",
                   "otp": "1234", "expires": datetime.now().timestamp() + 60}
        await bot._execute_confirmed_action(_make_update(), pending)
        self.assertEqual(pefi.config["PEFI_AUTO_BLOCK"], "false")


# ── Tests: _tick disabled guard ──────────────────────────────────────────

class TestPefiTickDisabled(unittest.IsolatedAsyncioTestCase):

    async def test_tick_skips_when_disabled(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.enabled = False
        pefi._store_ip_stats = MagicMock()

        await pefi._tick()
        pefi._store_ip_stats.assert_not_called()

    async def test_tick_runs_when_enabled(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        pefi = _make_pefi(db.name)
        pefi.enabled = True
        # Mock semua collectors agar tidak ada I/O nyata
        pefi._collect_connections = AsyncMock(return_value=[])
        pefi._collect_auth_failures = AsyncMock(return_value=[])
        pefi._collect_nginx_anomalies = AsyncMock(return_value=[])
        pefi._collect_kernel_stats = AsyncMock(return_value={})
        pefi._analyze_with_ai = AsyncMock(return_value=[])
        pefi.notifier.send = AsyncMock()

        await pefi._tick()
        pefi._collect_connections.assert_called_once()


# ── Tests: guard — non-admin tidak bisa akses /pefi ──────────────────────

class TestPefiGuard(unittest.IsolatedAsyncioTestCase):

    async def test_non_admin_blocked(self):
        bot, pefi = _make_bot()
        pefi.get_status = AsyncMock(return_value="status")
        # User bukan admin (id berbeda)
        update = _make_update(user_id=12345)
        await bot.cmd_pefi(update, _make_context([]))
        # get_status tidak boleh dipanggil
        pefi.get_status.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
