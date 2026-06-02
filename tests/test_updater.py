"""
Unit test Updater (self-update SyamAdmin dari GitHub — mesin tarball).
Jalankan: python3 -m unittest tests.test_updater -v   (tanpa jaringan, executor di-mock)
"""
import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.updater import Updater


def run(coro):
    return asyncio.run(coro)


class TestUpdater(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with open(os.path.join(self.dir, "VERSION"), "w") as f:
            f.write("3.1.0\n")
        self.ex = MagicMock()
        self.ex.run = AsyncMock()
        self.up = Updater(self.ex, config={"INSTALL_DIR": self.dir,
                                            "GITHUB_REPO": "Syamsuddin/SyamAdmin"})

    def test_local_version_read(self):
        self.assertEqual(self.up.get_local_version(), "3.1.0")

    def test_local_version_missing_default(self):
        os.remove(os.path.join(self.dir, "VERSION"))
        up = Updater(self.ex, config={"INSTALL_DIR": self.dir})
        # fallback ke VERSION root paket (mis. 3.2.0) atau 0.0.0 — keduanya valid string
        self.assertRegex(up.get_local_version(), r"^\d+\.\d+")

    def test_parse_and_compare(self):
        self.assertTrue(self.up.is_newer("3.2.0", "3.1.0"))
        self.assertTrue(self.up.is_newer("3.1.1", "3.1.0"))
        self.assertFalse(self.up.is_newer("3.1.0", "3.1.0"))
        self.assertFalse(self.up.is_newer("3.0.9", "3.1.0"))
        self.assertTrue(self.up.is_newer("10.0.0", "9.9.9"))  # numerik, bukan leksikografis

    def test_check_update_available(self):
        self.ex.run.return_value = {"success": True, "stdout": "3.2.0", "stderr": ""}
        res = run(self.up.check())
        self.assertTrue(res["ok"])
        self.assertEqual(res["local"], "3.1.0")
        self.assertEqual(res["remote"], "3.2.0")
        self.assertTrue(res["update_available"])

    def test_check_up_to_date(self):
        self.ex.run.return_value = {"success": True, "stdout": "3.1.0", "stderr": ""}
        res = run(self.up.check())
        self.assertTrue(res["ok"])
        self.assertFalse(res["update_available"])

    def test_check_remote_unreachable(self):
        self.ex.run.return_value = {"success": False, "stdout": "", "stderr": "curl: timeout"}
        res = run(self.up.check())
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_remote_version_strips_noise(self):
        self.ex.run.return_value = {"success": True, "stdout": "3.5.0\n\ngaris lain", "stderr": ""}
        self.assertEqual(run(self.up.get_remote_version()), "3.5.0")

    def test_trigger_update_detached_command(self):
        # sediakan script update.sh palsu di dir
        os.makedirs(os.path.join(self.dir, "scripts"), exist_ok=True)
        open(os.path.join(self.dir, "scripts", "update.sh"), "w").close()
        self.ex.run.return_value = {"success": True, "stdout": "", "stderr": ""}
        res = run(self.up.trigger_update())
        self.assertTrue(res["ok"])
        called_cmd = self.ex.run.call_args[0][0]
        self.assertIn("setsid", called_cmd)
        self.assertIn("nohup", called_cmd)
        self.assertIn("--repo", called_cmd)
        self.assertIn("Syamsuddin/SyamAdmin", called_cmd)
        self.assertTrue(called_cmd.strip().endswith("&"))

    def test_trigger_update_missing_script(self):
        # paksa path script ke lokasi tak ada → branch early-return (tanpa eksekusi)
        self.up._script_path = lambda: "/nonexistent/scripts/update.sh"
        res = run(self.up.trigger_update())
        self.assertFalse(res["ok"])
        self.assertIn("tidak ditemukan", res["error"])
        self.ex.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
