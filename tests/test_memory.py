"""
Unit test Memory Core (Pilar 2-4) + redaksi rahasia.
Jalankan: python3 -m unittest tests.test_memory -v   (tanpa API key / jaringan)
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.brain import AIBrain, redact_secrets


class TestRedaction(unittest.TestCase):
    def test_redacts_secrets(self):
        s = redact_secrets(
            "token 8767653946:AAEAvIR5UVFJ12BQaM83itfrJC2XNuVpqSI "
            "password=rahasia123 key sk-ant-abc123XYZ"
        )
        self.assertNotIn("AAEAvIR5", s)
        self.assertNotIn("rahasia123", s)
        self.assertNotIn("sk-ant-abc123XYZ", s)
        self.assertIn("[REDACTED]", s)

    def test_empty_safe(self):
        self.assertEqual(redact_secrets(""), "")


class TestMemoryCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.brain = AIBrain(api_key="", db_path=self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_user_memory_store_update_get(self):
        self.brain.store_user_preference("php", "8.3")
        self.brain.store_user_preference("php", "8.2")  # update
        self.brain.store_user_preference("tz", "Asia/Makassar")
        prefs = self.brain.get_user_preferences()
        self.assertEqual(prefs["php"], "8.2")
        self.assertEqual(prefs["tz"], "Asia/Makassar")

    def test_chat_history_sliding_window_and_redaction(self):
        for i in range(12):
            self.brain.add_to_chat_history("user", f"pesan-{i} password=bocor{i}")
            self.brain.add_to_chat_history("assistant", f"balas-{i}")
        h = self.brain.get_recent_history(limit=8)
        self.assertEqual(len(h), 8)                       # sliding window
        self.assertEqual(h[-1]["role"], "assistant")      # urutan kronologis
        joined = " ".join(t["content"] for t in h)
        self.assertNotIn("bocor", joined)                 # redaksi diterapkan

    def test_long_term_memory_relevance(self):
        self.brain.learn_lesson("incident", "Nginx gagal start karena port 80 dipakai apache")
        self.brain.learn_lesson("config_change", "Ubah port SSH ke 2222 untuk hardening")
        nginx = self.brain.query_long_term_memory("kenapa nginx error port")
        self.assertTrue(any("Nginx" in r for r in nginx))
        ssh = self.brain.query_long_term_memory("ssh hardening")
        self.assertTrue(any("SSH" in r for r in ssh))


if __name__ == "__main__":
    unittest.main()
