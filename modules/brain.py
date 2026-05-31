"""
AIBrain — Natural language command processing via Claude API.
Translates human instructions into sysadmin actions.
"""

import json
import logging
import os
import re
import sqlite3
from typing import Optional

logger = logging.getLogger("syamadmin.brain")

# Single source of truth for the model — override via CLAUDE_MODEL env var
_AI_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# Redaksi rahasia (#4 plan): cegah kredensial tersimpan plaintext di memori SQLite.
# Wizard provisioning men-generate & menampilkan password DB; tanpa redaksi, ia
# akan ikut tersimpan di chat_history / long_term_memory.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),                       # Anthropic API key
    re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b"),               # Telegram bot token
    re.compile(r"(?i)(password|passwd|pass|pwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
]


def redact_secrets(text: str) -> str:
    """Ganti pola rahasia (key, token, password) dengan [REDACTED]."""
    if not text:
        return text
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text

# Tarif harga per token (USD) — sesuaikan dengan model aktif.
# Haiku 4.5: $1 / 1M input, $5 / 1M output. Verifikasi berkala ke pricing resmi Anthropic.
_PRICE_INPUT_PER_TOKEN = 0.000001
_PRICE_OUTPUT_PER_TOKEN = 0.000005

SYSTEM_PROMPT = """Kamu adalah SyamAdmin, AI sysadmin agent yang mengelola server Ubuntu 22.04 VPS.
Kamu menerima perintah dalam bahasa Indonesia atau Inggris dari admin via Telegram.

Tugas kamu:
1. Pahami intent dari perintah admin
2. Tentukan modul mana yang harus dijalankan
3. Return JSON response dengan aksi yang harus dilakukan

Modul yang tersedia:
- provisioner: Setup LEMP stack (nginx, mysql, php), install packages
- security: SSH hardening, fail2ban, audit, rootkit scan
- firewall: UFW rules management (allow/deny ports, list rules)
- monitor: System metrics, service status, resource usage
- site_manager: Nginx vhost management, SSL certificates, domain setup
- backup: Database backup, file backup, restore
- executor: Direct shell command (HATI-HATI, hanya untuk advanced users)

Untuk MENJALANKAN perintah, PANGGIL tool `execute_sysadmin_action` dengan argumen yang sesuai.
Jika perintah MAJEMUK (beberapa aksi sekaligus, mis. "backup db lalu restart nginx lalu ubah port ssh"),
isi field `steps` dengan daftar aksi BERURUTAN sesuai urutan diminta. Untuk aksi TUNGGAL, kosongkan `steps`
dan isi module/action/params seperti biasa.
Jika perintah tidak jelas/ambigu, JANGAN panggil tool — cukup balas dengan teks pertanyaan
klarifikasi dalam bahasa Indonesia.

Contoh aksi per modul (gunakan nama alias berikut, sistem akan menerjemahkan):
- provisioner: install_lemp, install_package, setup_composer
- security: harden_ssh, setup_fail2ban, audit, scan_rootkit, check_updates
- firewall: allow_port, deny_port, list_rules, reset, status
- monitor: status, services, top_processes, disk_usage, connections
- site_manager: add_site, remove_site, list_sites, enable_ssl, disable_site
- backup: backup_db, backup_files, backup_all, list_backups, restore
- executor: service_restart (params: {"service": "..."}), run_command (params: {"command": "..."})

PENTING tentang STATE server:
- Jika konteks menunjukkan "LEMP stack: BELUM terpasang", JANGAN rutekan ke add_site atau enable_ssl.
  JANGAN panggil tool — balas teks yang menyarankan user menjalankan `/provision` atau `/setup` dulu.
- Jika user minta restore, set confirmation_needed=true karena restore bersifat DESTRUKTIF.

Jika perintah berbahaya atau ambigu, set confirmation_needed=true dan jelaskan risikonya di field message.
Jika perintah tidak jelas, JANGAN panggil tool — balas teks klarifikasi.
"""

# Definisi tool untuk native tool-use (#2): menggantikan parsing JSON-dalam-teks
# yang rapuh. Model dipaksa menghasilkan struktur valid; module dibatasi enum.
DISPATCH_TOOL = {
    "name": "execute_sysadmin_action",
    "description": (
        "Jalankan SATU aksi sysadmin pada server Ubuntu. Pilih module dan action "
        "yang tepat berdasarkan perintah admin serta konteks state server."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "description": "deskripsi singkat maksud perintah"},
            "module": {
                "type": "string",
                "enum": ["provisioner", "security", "firewall", "monitor",
                         "site_manager", "backup", "executor"],
                "description": "modul tujuan",
            },
            "action": {"type": "string", "description": "nama aksi sesuai daftar alias yang diketahui"},
            "params": {
                "type": "object",
                "description": "parameter aksi, mis. {\"service\":\"nginx\"} atau {\"command\":\"...\"}",
                "additionalProperties": True,
            },
            "confirmation_needed": {
                "type": "boolean",
                "description": "true bila aksi berbahaya, destruktif, atau ambigu",
            },
            "message": {"type": "string", "description": "pesan ramah untuk admin dalam bahasa Indonesia"},
            "steps": {
                "type": "array",
                "description": (
                    "Untuk perintah MAJEMUK: daftar aksi berurutan. Kosongkan untuk aksi tunggal."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "module": {
                            "type": "string",
                            "enum": ["provisioner", "security", "firewall", "monitor",
                                     "site_manager", "backup", "executor"],
                        },
                        "action": {"type": "string"},
                        "params": {"type": "object", "additionalProperties": True},
                        "message": {"type": "string", "description": "deskripsi singkat langkah ini"},
                    },
                    "required": ["module", "action", "message"],
                },
            },
        },
        "required": ["intent", "module", "action", "confirmation_needed", "message"],
    },
}


class AIBrain:
    """AI decision engine for natural language sysadmin commands."""

    def __init__(self, api_key: str = "", db_path: str = "/var/lib/syamadmin/syamadmin.db"):
        self.api_key = api_key
        self.db_path = db_path
        self._client = None
        self.enabled = bool(api_key)
        self.last_error = None
        self.model = _AI_MODEL
        self._ensure_db()

        if not self.enabled:
            logger.warning("AI Brain disabled — no ANTHROPIC_API_KEY configured")

    def _ensure_db(self):
        """Pastikan tabel token_usage + Memory Core (Pilar 2-4) ada — mandiri."""
        self._fts_enabled = False
        try:
            conn = sqlite3.connect(self.db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    action TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    model TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    category TEXT NOT NULL,
                    summary TEXT NOT NULL
                );
            """)
            conn.commit()
            # FTS5 untuk pencarian relevan long_term_memory — opsional & degradasi mulus
            try:
                conn.executescript("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS long_term_fts
                        USING fts5(summary, content='long_term_memory', content_rowid='id');
                    CREATE TRIGGER IF NOT EXISTS ltm_ai AFTER INSERT ON long_term_memory BEGIN
                        INSERT INTO long_term_fts(rowid, summary) VALUES (new.id, new.summary);
                    END;
                    CREATE TRIGGER IF NOT EXISTS ltm_ad AFTER DELETE ON long_term_memory BEGIN
                        INSERT INTO long_term_fts(long_term_fts, rowid, summary)
                        VALUES('delete', old.id, old.summary);
                    END;
                """)
                conn.commit()
                self._fts_enabled = True
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 tak tersedia, long_term_memory pakai LIKE: {e}")
            conn.close()
        except Exception as e:
            logger.warning(f"Brain DB init warning: {e}")

    def log_token_usage(self, action: str, input_tokens: int, output_tokens: int, model: str):
        """Log token consumption metrics into SQLite database."""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO token_usage (action, input_tokens, output_tokens, model) VALUES (?, ?, ?, ?)",
                (action[:200], input_tokens, output_tokens, model)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Token logging warning: {e}")

    def get_token_statistics(self) -> dict:
        """
        Calculate total token usage and estimate API costs.
        Tarif mengikuti _PRICE_*_PER_TOKEN (default: Haiku 4.5 = $1/1M in, $5/1M out).
        """
        stats = {
            "total_input": 0,
            "total_output": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_idr": 0.0,
            "calls_count": 0,
            "api_status": "🟢 Active & Enabled" if self.enabled else "🔴 Disabled (Missing ANTHROPIC_API_KEY)"
        }

        if self.last_error:
            stats["api_status"] = f"⚠️ API Error: {self.last_error}"

        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute("SELECT SUM(input_tokens), SUM(output_tokens), COUNT(id) FROM token_usage")
            row = cur.fetchone()
            conn.close()

            if row and row[0] is not None:
                stats["total_input"] = row[0]
                stats["total_output"] = row[1]
                stats["total_tokens"] = row[0] + row[1]
                stats["calls_count"] = row[2]

                stats["cost_usd"] = (row[0] * _PRICE_INPUT_PER_TOKEN) + (row[1] * _PRICE_OUTPUT_PER_TOKEN)
                # Assume $1 USD = Rp 16,300
                stats["cost_idr"] = stats["cost_usd"] * 16300.0
        except Exception as e:
            logger.warning(f"Failed to fetch token stats: {e}")

        return stats

    # ==================== Memory Core (Pilar 2-4) ====================

    def store_user_preference(self, key: str, value: str) -> None:
        """Pilar 2: simpan/perbarui preferensi admin."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO user_memory (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                (key[:64], str(value)[:512]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"store_user_preference warning: {e}")

    def get_user_preferences(self) -> dict:
        """Pilar 2: ambil semua preferensi admin."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT key, value FROM user_memory").fetchall()
            conn.close()
            return {k: v for k, v in rows}
        except Exception:
            return {}

    def add_to_chat_history(self, role: str, content: str) -> None:
        """Pilar 3: simpan satu turn percakapan (sudah diredaksi)."""
        if role not in ("user", "assistant") or not content:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO chat_history (role, content) VALUES (?, ?)",
                (role, redact_secrets(content)[:2000]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"add_to_chat_history warning: {e}")

    def get_recent_history(self, limit: int = 8) -> list:
        """Pilar 3: ambil N turn terakhir (urutan kronologis) sebagai message turns."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [{"role": r, "content": c} for r, c in reversed(rows)]
        except Exception:
            return []

    def learn_lesson(self, category: str, summary: str) -> None:
        """Pilar 4: catat pelajaran insiden/konfigurasi (sudah diredaksi)."""
        if not summary:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO long_term_memory (category, summary) VALUES (?, ?)",
                (category[:32], redact_secrets(summary)[:1000]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"learn_lesson warning: {e}")

    def get_memory_stats(self) -> dict:
        """Hitung jumlah baris tiap pilar memori (untuk laporan /status)."""
        out = {"chat": 0, "lessons": 0, "prefs": 0}
        try:
            conn = sqlite3.connect(self.db_path)
            out["chat"] = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
            out["lessons"] = conn.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0]
            out["prefs"] = conn.execute("SELECT COUNT(*) FROM user_memory").fetchone()[0]
            conn.close()
        except Exception:
            pass
        return out

    def query_long_term_memory(self, query_text: str, top_n: int = 3) -> list:
        """Pilar 4: cari pelajaran relevan via FTS5 (fallback LIKE)."""
        if not query_text:
            return []
        try:
            conn = sqlite3.connect(self.db_path)
            if self._fts_enabled:
                # Ambil token kata kunci → query FTS5 OR
                terms = [t for t in re.findall(r"[A-Za-z0-9]{3,}", query_text.lower())][:6]
                if not terms:
                    conn.close()
                    return []
                fts_q = " OR ".join(terms)
                rows = conn.execute(
                    "SELECT m.summary FROM long_term_fts f "
                    "JOIN long_term_memory m ON m.id = f.rowid "
                    "WHERE long_term_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts_q, top_n),
                ).fetchall()
            else:
                like = f"%{query_text[:50]}%"
                rows = conn.execute(
                    "SELECT summary FROM long_term_memory WHERE summary LIKE ? "
                    "ORDER BY id DESC LIMIT ?",
                    (like, top_n),
                ).fetchall()
            conn.close()
            return [r[0] for r in rows]
        except Exception as e:
            logger.warning(f"query_long_term_memory warning: {e}")
            return []

    def _get_client(self):
        if self._client is None and self.enabled:
            import anthropic
            # AsyncAnthropic agar tidak memblokir event loop saat memanggil API
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    def _log_usage(self, action: str, response) -> None:
        """Log token usage jika response mengandung usage metadata."""
        if hasattr(response, "usage") and response.usage:
            self.log_token_usage(
                action=action,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=_AI_MODEL,
            )

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Ekstrak JSON dari response AI, termasuk dari markdown code block."""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)

    async def process_command(
        self, user_message: str, context: str = "", history: list = None
    ) -> dict:
        """
        Process a natural language command and return structured action.

        history: daftar turn percakapan [{role, content}, ...] (Pilar 3) untuk
        konteks multi-turn — dikirim sebagai message turns, BUKAN di-cache.

        Returns dict with: intent, module, action, params, confirmation_needed,
        message, dan (opsional) steps untuk perintah majemuk.
        """
        if not self.enabled:
            return self._fallback_parse(user_message)

        try:
            client = self._get_client()
            prompt = user_message
            if context:
                prompt = f"Konteks server saat ini:\n{context}\n\nPerintah admin:\n{user_message}"

            # Riwayat (volatil) di blok messages — tidak di-cache. Prefix statis
            # (system+tools) yang di-cache.
            messages = list(history or [])
            messages.append({"role": "user", "content": prompt})

            response = await client.messages.create(
                model=_AI_MODEL,
                max_tokens=1024,
                # Prompt caching (#7): tandai prefix statis (tools + system) sebagai
                # cacheable agar tidak ditagih penuh tiap panggilan /ai. Cache-control
                # pada blok system mencakup tools yang mendahuluinya. Aktif bila prefix
                # >= minimum token model (Haiku 2048; Sonnet/Opus 1024) — di bawah itu
                # ditandai aman tanpa efek, dan otomatis berlaku saat prompt membesar.
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=[DISPATCH_TOOL],
                messages=messages,
            )

            self.last_error = None
            self._log_usage(f"command: {user_message[:150]}", response)

            # Cari blok tool_use → struktur dijamin valid oleh skema tool
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    inp = block.input or {}
                    result = {
                        "intent": inp.get("intent", ""),
                        "module": inp.get("module", ""),
                        "action": inp.get("action", ""),
                        "params": inp.get("params") or {},
                        "confirmation_needed": bool(inp.get("confirmation_needed", False)),
                        "message": inp.get("message", ""),
                    }
                    # Multi-step (#planner): sertakan steps bila ada & valid (>1)
                    steps = inp.get("steps") or []
                    if isinstance(steps, list) and len(steps) > 1:
                        result["steps"] = [
                            {
                                "module": s.get("module", ""),
                                "action": s.get("action", ""),
                                "params": s.get("params") or {},
                                "message": s.get("message", ""),
                            }
                            for s in steps
                            if s.get("module") and s.get("action")
                        ]
                    logger.info(
                        f"AI tool_use: module={result['module']}, action={result['action']}, "
                        f"steps={len(result.get('steps', []))}, confirm={result['confirmation_needed']}"
                    )
                    return result

            # Tidak ada tool_use → model memilih klarifikasi (jawaban teks)
            text = "".join(
                getattr(b, "text", "") for b in response.content
                if getattr(b, "type", None) == "text"
            ).strip()
            return {
                "intent": "clarify",
                "module": "brain",
                "action": "clarify",
                "params": {},
                "confirmation_needed": False,
                "message": text or "Bisa diperjelas maksud perintahnya?",
            }

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"AI Brain error: {e}")
            return self._fallback_parse(user_message)

    def _fallback_parse(self, message: str) -> dict:
        """Simple keyword-based parser as fallback when AI is unavailable."""
        msg = message.lower().strip()

        # Peta keyword -> modul.aksi (semua aksi valid, dijamin alias map)
        mappings = [
            (["status", "kesehatan", "health"], "monitor", "status", {}),
            (["service", "layanan", "servis"], "monitor", "services", {}),
            (["disk", "storage", "penyimpanan"], "monitor", "disk_usage", {}),
            (["proses", "process", "cpu tinggi"], "monitor", "top_processes", {}),
            (["koneksi", "connection", "network"], "monitor", "connections", {}),
            (["provision", "install lemp", "setup server"], "provisioner", "install_lemp", {}),
            (["firewall", "ufw"], "firewall", "status", {}),
            (["security", "keamanan", "audit"], "security", "audit", {}),
            (["site", "domain", "vhost"], "site_manager", "list_sites", {}),
            (["backup"], "backup", "backup_all", {}),
            (["restart nginx"], "executor", "service_restart", {"service": "nginx"}),
            (["restart mysql"], "executor", "service_restart", {"service": "mysql"}),
            (["restart php"], "executor", "service_restart", {"service": "php8.3-fpm"}),
            (["update", "upgrade"], "security", "check_updates", {}),
            (["log", "logs"], "monitor", "services", {}),  # fallback aman; /logs punya command sendiri
        ]

        for keywords, module, action, params in mappings:
            if any(kw in msg for kw in keywords):
                return {
                    "intent": f"Fallback match: {action}",
                    "module": module,
                    "action": action,
                    "params": params,
                    "confirmation_needed": False,
                    "message": f"Menjalankan {action} via {module}...",
                }

        return {
            "intent": "unknown",
            "module": "brain",
            "action": "clarify",
            "params": {},
            "confirmation_needed": False,
            "message": (
                "Maaf, saya tidak mengerti perintah itu.\n\n"
                "Coba gunakan:\n"
                "• `/status` — cek status server\n"
                "• `/services` — cek status layanan\n"
                "• `/provision` — setup LEMP stack\n"
                "• `/firewall` — manage firewall\n"
                "• `/security` — security audit\n"
                "• `/logs <service>` — lihat log service\n"
                "• `/help` — bantuan lengkap"
            ),
        }

    async def analyze_logs(self, log_content: str) -> str:
        """Use AI to analyze log content and identify issues."""
        if not self.enabled:
            return "AI Brain tidak aktif. Set ANTHROPIC_API_KEY untuk mengaktifkan analisis log."

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=_AI_MODEL,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Analisis log server berikut dan identifikasi masalah, "
                        f"ancaman keamanan, atau anomali. "
                        f"Jawab singkat dalam bahasa Indonesia:\n\n"
                        f"```\n{log_content[:3000]}\n```"
                    ),
                }],
            )

            self.last_error = None
            self._log_usage("analyze_logs", response)
            return response.content[0].text
        except Exception as e:
            self.last_error = str(e)
            return f"Gagal menganalisis log: {e}"

    async def diagnose_crash(self, service: str, log_content: str) -> dict:
        """Use AI to analyze a service crash and recommend a dynamic Auto-Repair command."""
        fallback_res = {
            "cause": "Service terdeteksi berhenti atau tidak merespons.",
            "solution": "Mencoba merestart service.",
            "repair_command": f"systemctl restart {service}",
            "risk": "Restart service dapat menyebabkan downtime sesaat."
        }
        if not self.enabled:
            return fallback_res

        try:
            client = self._get_client()
            prompt = (
                f"Layanan yang mengalami crash: {service}\n\n"
                f"Log dari layanan tersebut:\n"
                f"```\n{log_content[:2500]}\n```"
            )
            response = await client.messages.create(
                model=_AI_MODEL,
                max_tokens=1024,
                system=(
                    "Kamu adalah SyamAdmin, agen AI sysadmin. Tugas kamu adalah mendiagnosis log dari layanan yang mengalami crash dan menyusun usulan perintah perbaikan otomatis (Auto-Repair) yang AMAN.\n"
                    "Gunakan bahasa Indonesia sederhana yang ramah pemula.\n\n"
                    "SELALU balas dalam format JSON murni:\n"
                    "{\n"
                    "    \"cause\": \"penjelasan penyebab dalam bahasa Indonesia sederhana\",\n"
                    "    \"solution\": \"langkah penjelasan solusi\",\n"
                    "    \"repair_command\": \"perintah bash aman tunggal untuk memperbaiki masalah tersebut (tidak boleh berisi filter command yang dilarang seperti rm -rf /)\",\n"
                    "    \"risk\": \"risiko jika perintah ini dijalankan\"\n"
                    "}"
                ),
                messages=[{"role": "user", "content": prompt}],
            )

            self.last_error = None
            self._log_usage(f"diagnose_crash: {service}", response)
            return self._extract_json(response.content[0].text)
        except Exception as e:
            self.last_error = str(e)
            logger.warning(f"Failed to diagnose crash: {e}")
            return fallback_res

    async def parse_cron_instruction(self, instruction: str) -> dict:
        """Parse natural language cron schedule request into a cron expression and action."""
        fallback_res = {
            "success": False,
            "cron_expression": "",
            "command": "",
            "readable_summary": "",
            "message": "Maaf, saya tidak dapat memahami permintaan jadwal tersebut. Silakan perjelas waktu penjadwalannya."
        }
        if not self.enabled:
            return fallback_res

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=_AI_MODEL,
                max_tokens=1024,
                system=(
                    "Kamu adalah SyamAdmin, agen AI sysadmin. Tugas kamu adalah menerjemahkan permintaan penjadwalan bahasa alami admin menjadi ekspresi cron standar Linux.\n"
                    "Tindakan/Command yang didukung oleh SyamAdmin:\n"
                    "- backup_all (Backup penuh)\n"
                    "- backup_db (Backup database saja)\n"
                    "- backup_files (Backup file situs saja)\n"
                    "- security_audit (Menjalankan audit keamanan)\n"
                    "- rkhunter_scan (Menjalankan scan rootkit)\n\n"
                    "SELALU balas dalam format JSON murni:\n"
                    "{\n"
                    "    \"success\": true/false,\n"
                    "    \"cron_expression\": \"ekspresi cron standar (misal: '0 3 * * *')\",\n"
                    "    \"command\": \"nama tindakan dari daftar di atas (misal: 'backup_all')\",\n"
                    "    \"readable_summary\": \"penjelasan jadwal yang mudah dibaca dalam bahasa Indonesia (misal: 'setiap hari pukul 03:00 pagi')\",\n"
                    "    \"message\": \"konfirmasi ramah dalam bahasa Indonesia\"\n"
                    "}"
                ),
                messages=[{"role": "user", "content": instruction}],
            )

            self.last_error = None
            self._log_usage(f"parse_cron: {instruction[:50]}", response)
            return self._extract_json(response.content[0].text)
        except Exception as e:
            self.last_error = str(e)
            return fallback_res

    async def generate_optimization_report(self, metrics_summary: str) -> dict:
        """Analyze resource utilization metrics over time and recommend configurations."""
        fallback_res = {
            "report": "Metrik server terpantau normal. Belum ada rekomendasi optimasi khusus saat ini.",
            "has_recommendation": False,
            "target_service": "",
            "optimization_command": "",
            "risk": ""
        }
        if not self.enabled:
            return fallback_res

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=_AI_MODEL,
                max_tokens=1536,
                system=(
                    "Kamu adalah SyamAdmin, agen AI sysadmin. Tugas kamu adalah menganalisis ringkasan tren utilitas server (CPU, RAM, Disk, Swap) dan memberikan usulan optimasi sistem (Nginx, MySQL, Swap, PHP-FPM) yang paling cocok.\n"
                    "Gunakan bahasa Indonesia sederhana yang ramah pemula.\n\n"
                    "SELALU balas dalam format JSON murni:\n"
                    "{\n"
                    "    \"report\": \"analisis mendalam tren performa dan penjelasan usulan optimasi secara terperinci bagi pemula\",\n"
                    "    \"has_recommendation\": true/false,\n"
                    "    \"target_service\": \"layanan target (misal: mysql, nginx, php, atau swap)\",\n"
                    "    \"optimization_command\": \"perintah bash aman tunggal untuk menerapkan optimasi (misal jika swap: membuat swap file, jika mysql: memodifikasi konfigurasi aman)\",\n"
                    "    \"risk\": \"penjelasan risiko tindakan optimasi\"\n"
                    "}"
                ),
                messages=[{"role": "user", "content": f"Ringkasan tren utilitas server:\n{metrics_summary}"}],
            )

            self.last_error = None
            self._log_usage("generate_optimization", response)
            return self._extract_json(response.content[0].text)
        except Exception as e:
            self.last_error = str(e)
            return fallback_res

    async def analyze_security_threats(self, log_summary: str) -> str:
        """Analyze security logs (ssh auth, fail2ban) and generate an executive report."""
        if not self.enabled:
            return "AI Brain tidak aktif. Set ANTHROPIC_API_KEY untuk laporan analisis keamanan pintar."

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=_AI_MODEL,
                max_tokens=1536,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Menganalisis ringkasan aktivitas log keamanan server (brute-force login, Fail2Ban bans) di bawah ini "
                        f"dan buatlah laporan analisis ancaman keamanan eksekutif dalam bahasa Indonesia.\n"
                        f"Rangkum asal negara penyerang terbanyak, port yang ditargetkan, serta berikan rekomendasi "
                        f"tindakan hardening yang harus diambil (seperti mengganti port SSH):\n\n"
                        f"```\n{log_summary}\n```"
                    ),
                }],
            )

            self.last_error = None
            self._log_usage("analyze_security_threats", response)
            return response.content[0].text
        except Exception as e:
            self.last_error = str(e)
            return f"Gagal menganalisis keamanan: {e}"

    async def explain_error(self, operation: str, stderr: str) -> str:
        """Ubah pesan error teknis jadi penjelasan ramah-pemula + langkah perbaikan."""
        if not self.enabled:
            return ""  # fallback: pemanggil tetap tampilkan stderr mentah
        try:
            client = self._get_client()
            response = await client.messages.create(
                model=_AI_MODEL, max_tokens=512,
                system=("Kamu SyamAdmin. Jelaskan error sysadmin berikut dalam bahasa "
                        "Indonesia sederhana untuk pemula: apa artinya & 1-2 langkah perbaikan. "
                        "Singkat, tanpa jargon."),
                messages=[{"role": "user",
                           "content": f"Operasi: {operation}\nError:\n```\n{stderr[:1500]}\n```"}],
            )
            self.last_error = None
            self._log_usage(f"explain_error: {operation}", response)
            return response.content[0].text.strip()
        except Exception as e:
            self.last_error = str(e)
            return ""
