"""
Unit test Profil Admin & Konteks Sistem (data awal SyamAdmin).
Jalankan: python3 -m unittest tests.test_profile -v   (tanpa API key / jaringan)
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.brain import AIBrain, PROFILE_FIELDS, _PROFILE_KEY_INDEX


class TestProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.brain = AIBrain(api_key="", db_path=self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_schema_keys_unique(self):
        keys = [f["key"] for f in PROFILE_FIELDS]
        self.assertEqual(len(keys), len(set(keys)), "key profil harus unik")
        self.assertEqual(len(_PROFILE_KEY_INDEX), len(PROFILE_FIELDS))
        for f in PROFILE_FIELDS:
            self.assertIn(f["scope"], ("profile", "server"))

    def test_empty_then_set(self):
        self.assertTrue(self.brain.is_profile_empty())
        self.assertEqual(self.brain.get_profile(), {})
        self.assertTrue(self.brain.set_profile_value("name", "Budi"))
        self.assertFalse(self.brain.is_profile_empty())
        self.assertEqual(self.brain.get_profile()["name"], "Budi")

    def test_reject_unknown_field(self):
        self.assertFalse(self.brain.set_profile_value("tidakada", "x"))
        self.assertTrue(self.brain.is_profile_empty())

    def test_scope_prefix_storage(self):
        self.brain.set_profile_value("name", "Budi")     # profile.*
        self.brain.set_profile_value("role", "produksi")  # server.*
        prof = self.brain.get_profile()
        self.assertEqual(prof["name"], "Budi")
        self.assertEqual(prof["role"], "produksi")

    def test_preferences_exclude_profile(self):
        self.brain.store_user_preference("php", "8.3")
        self.brain.set_profile_value("name", "Budi")
        self.brain.set_profile_value("role", "produksi")
        prefs = self.brain.get_user_preferences()
        self.assertIn("php", prefs)
        self.assertNotIn("profile.name", prefs)
        self.assertNotIn("server.role", prefs)

    def test_clear_profile_keeps_generic_prefs(self):
        self.brain.store_user_preference("php", "8.3")
        self.brain.set_profile_value("name", "Budi")
        self.brain.clear_profile()
        self.assertTrue(self.brain.is_profile_empty())
        self.assertEqual(self.brain.get_user_preferences().get("php"), "8.3")

    def test_nickname_fallback(self):
        self.assertEqual(self.brain.get_admin_nickname(), "Boss")
        self.brain.set_profile_value("name", "Budi")
        self.assertEqual(self.brain.get_admin_nickname(), "Budi")
        self.brain.set_profile_value("nickname", "Pak Bud")
        self.assertEqual(self.brain.get_admin_nickname(), "Pak Bud")

    def test_timezone_resolution(self):
        # default (tanpa profil / env) → Asia/Jakarta
        os.environ.pop("TZ", None)
        self.assertEqual(self.brain.get_admin_timezone(), "Asia/Jakarta")
        self.brain.set_profile_value("timezone", "Asia/Makassar")
        self.assertEqual(self.brain.get_admin_timezone(), "Asia/Makassar")

    def test_profile_context_human_readable(self):
        self.assertEqual(self.brain.get_profile_context(), "")
        self.brain.set_profile_value("name", "Budi")
        self.brain.set_profile_value("role", "produksi")
        ctx = self.brain.get_profile_context()
        self.assertIn("Profil admin", ctx)
        self.assertIn("Budi", ctx)
        self.assertIn("Konteks server", ctx)
        self.assertIn("produksi", ctx)

    def test_system_context_has_date_time(self):
        self.brain.set_profile_value("timezone", "Asia/Jakarta")
        ctx = self.brain.get_system_context()
        self.assertIn("Waktu sekarang", ctx)
        self.assertIn("pukul", ctx)
        # salah satu periode salam harus muncul
        self.assertTrue(any(s in ctx for s in ("pagi", "siang", "sore", "malam")))

    def test_system_context_invalid_tz_graceful(self):
        self.brain.set_profile_value("timezone", "Zona/Ngawur")
        ctx = self.brain.get_system_context()  # tidak boleh raise
        self.assertIn("Waktu sekarang", ctx)


if __name__ == "__main__":
    unittest.main()
