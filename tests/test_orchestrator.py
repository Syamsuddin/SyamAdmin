"""
Unit test Multi-step Orchestrator (deteksi destruktif, render, halt-on-failure).
Jalankan: python3 -m unittest tests.test_orchestrator -v   (tanpa jaringan)
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.telegram_bot import SyamAdminBot


class FakeMsg:
    def __init__(self):
        self.text = None

    async def edit_text(self, text, **kw):
        self.text = text
        return self


class FakeMessage:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        m = FakeMsg()
        m.text = text
        self.sent.append(text)
        return m


class FakeUpdate:
    def __init__(self):
        self.message = FakeMessage()


def make_bot():
    return SyamAdminBot(token="x", admin_id=1, modules={"brain": _FakeBrain()}, server_name="t")


class _FakeBrain:
    def add_to_chat_history(self, *a, **k): pass
    def learn_lesson(self, *a, **k): self.learned = True


class TestDestructiveDetection(unittest.TestCase):
    def test_run_command_is_destructive(self):
        self.assertTrue(SyamAdminBot._step_is_destructive(
            {"module": "executor", "action": "run_command"}))

    def test_change_ssh_port_is_destructive(self):
        self.assertTrue(SyamAdminBot._step_is_destructive(
            {"module": "security", "action": "change_ssh_port"}))

    def test_status_is_safe(self):
        self.assertFalse(SyamAdminBot._step_is_destructive(
            {"module": "monitor", "action": "status"}))


class TestProgressRender(unittest.TestCase):
    def test_render_shows_all_steps(self):
        steps = [{"module": "backup", "action": "backup_db", "message": "Backup DB"},
                 {"module": "monitor", "action": "status", "message": "Cek status"}]
        out = SyamAdminBot._render_plan_progress(steps, ["done", "run"])
        self.assertIn("Backup DB", out)
        self.assertIn("Cek status", out)
        self.assertIn("✅", out)
        self.assertIn("⏳", out)


class TestHaltOnFailure(unittest.TestCase):
    def test_plan_halts_on_failed_step(self):
        bot = make_bot()
        calls = []

        async def fake_action(step):
            calls.append(step["action"])
            # langkah ke-2 gagal
            return "❌ gagal" if step["action"] == "fail_step" else "✅ ok"

        async def fake_augment(op, text):
            return text

        bot._execute_ai_action = fake_action
        bot._augment_failure = fake_augment

        plan = [
            {"module": "monitor", "action": "ok_step", "message": "satu"},
            {"module": "executor", "action": "fail_step", "message": "dua"},
            {"module": "monitor", "action": "never", "message": "tiga"},
        ]
        update = FakeUpdate()
        asyncio.run(bot._execute_multi_step_plan(update, plan))

        # langkah ke-3 TIDAK boleh dijalankan (halt setelah gagal)
        self.assertEqual(calls, ["ok_step", "fail_step"])
        self.assertFalse(bot._plan_running)  # flag direset

    def test_plan_success_learns_lesson(self):
        bot = make_bot()

        async def fake_action(step):
            return "✅ ok"
        bot._execute_ai_action = fake_action

        plan = [{"module": "monitor", "action": "a", "message": "x"},
                {"module": "monitor", "action": "b", "message": "y"}]
        asyncio.run(bot._execute_multi_step_plan(FakeUpdate(), plan))
        self.assertTrue(getattr(bot.modules["brain"], "learned", False))


if __name__ == "__main__":
    unittest.main()
