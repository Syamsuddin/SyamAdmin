"""
AIBrain — Natural language command processing via Claude API.
Translates human instructions into sysadmin actions.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("syamadmin.brain")

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

SELALU respond dalam format JSON:
{
    "intent": "deskripsi singkat apa yang diminta",
    "module": "nama_modul",
    "action": "nama_aksi",
    "params": {},
    "confirmation_needed": true/false,
    "message": "pesan untuk admin dalam bahasa Indonesia"
}

Contoh aksi per modul:
- provisioner: install_lemp, install_package, setup_composer
- security: harden_ssh, setup_fail2ban, audit, scan_rootkit, check_updates
- firewall: allow_port, deny_port, list_rules, reset, status
- monitor: status, services, top_processes, disk_usage, connections
- site_manager: add_site, remove_site, list_sites, enable_ssl, disable_site
- backup: backup_db, backup_files, backup_all, list_backups, restore
- executor: run_command (params: {"command": "..."})

Jika perintah berbahaya atau ambigu, set confirmation_needed=true dan jelaskan risikonya di message.
Jika perintah tidak jelas, minta klarifikasi di message dan set action="clarify".
"""


class AIBrain:
    """AI decision engine for natural language sysadmin commands."""

    def __init__(self, api_key: str = "", db_path: str = "/var/lib/syamadmin/syamadmin.db"):
        self.api_key = api_key
        self.db_path = db_path
        self._client = None
        self.enabled = bool(api_key)
        self.last_error = None
        self._ensure_db()

        if not self.enabled:
            logger.warning("AI Brain disabled — no ANTHROPIC_API_KEY configured")

    def _ensure_db(self):
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    action TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    model TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Token DB init warning: {e}")

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
        Claude 3.5 Sonnet: $3.00 / 1M input tokens, $15.00 / 1M output tokens.
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
                
                # Input: $3/1M, Output: $15/1M
                stats["cost_usd"] = (row[0] * 0.000003) + (row[1] * 0.000015)
                # Assume $1 USD = Rp 16,300
                stats["cost_idr"] = stats["cost_usd"] * 16300.0
        except Exception as e:
            logger.warning(f"Failed to fetch token stats: {e}")

        return stats

    def _get_client(self):
        if self._client is None and self.enabled:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    async def process_command(
        self, user_message: str, context: str = ""
    ) -> dict:
        """
        Process a natural language command and return structured action.

        Returns dict with: intent, module, action, params, confirmation_needed, message
        """
        if not self.enabled:
            return self._fallback_parse(user_message)

        try:
            client = self._get_client()
            prompt = user_message
            if context:
                prompt = f"Konteks server saat ini:\n{context}\n\nPerintah admin:\n{user_message}"

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            # Clear last error on successful call
            self.last_error = None

            # Capture usage metrics
            if hasattr(response, 'usage') and response.usage:
                self.log_token_usage(
                    action=f"command: {user_message}",
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    model="claude-sonnet-4-20250514"
                )

            text = response.content[0].text.strip()

            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            result = json.loads(text)
            logger.info(f"AI parsed: intent={result.get('intent')}, module={result.get('module')}, action={result.get('action')}")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"AI response not valid JSON: {e}")
            return {
                "intent": "parse_error",
                "module": "brain",
                "action": "clarify",
                "params": {},
                "confirmation_needed": False,
                "message": f"Maaf, saya tidak bisa memahami perintah itu. Bisa diperjelas?\n\nPerintah: _{user_message}_",
            }
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"AI Brain error: {e}")
            return self._fallback_parse(user_message)

    def _fallback_parse(self, message: str) -> dict:
        """Simple keyword-based parser as fallback when AI is unavailable."""
        msg = message.lower().strip()

        # Simple keyword mapping
        mappings = [
            (["status", "kesehatan", "health"], "monitor", "status", {}),
            (["service", "layanan", "servis"], "monitor", "services", {}),
            (["provision", "install lemp", "setup server"], "provisioner", "install_lemp", {}),
            (["firewall", "ufw"], "firewall", "status", {}),
            (["security", "keamanan", "audit"], "security", "audit", {}),
            (["site", "domain", "vhost"], "site_manager", "list_sites", {}),
            (["backup"], "backup", "backup_all", {}),
            (["restart nginx"], "executor", "service_restart", {"service": "nginx"}),
            (["restart mysql"], "executor", "service_restart", {"service": "mysql"}),
            (["restart php"], "executor", "service_restart", {"service": "php8.3-fpm"}),
            (["update", "upgrade"], "security", "check_updates", {}),
            (["disk", "storage"], "monitor", "disk_usage", {}),
            (["log", "logs"], "monitor", "recent_logs", {}),
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
                "• `/help` — bantuan lengkap"
            ),
        }

    async def analyze_logs(self, log_content: str) -> str:
        """Use AI to analyze log content and identify issues."""
        if not self.enabled:
            return "AI Brain tidak aktif. Set ANTHROPIC_API_KEY untuk mengaktifkan analisis log."

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
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

            # Capture usage metrics for log analysis
            if hasattr(response, 'usage') and response.usage:
                self.log_token_usage(
                    action="analyze_logs",
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    model="claude-sonnet-4-20250514"
                )

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
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
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
            if hasattr(response, 'usage') and response.usage:
                self.log_token_usage(
                    action=f"diagnose_crash: {service}",
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    model="claude-sonnet-4-20250514"
                )

            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
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
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
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
            if hasattr(response, 'usage') and response.usage:
                self.log_token_usage(
                    action=f"parse_cron: {instruction[:50]}",
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    model="claude-sonnet-4-20250514"
                )

            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
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
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
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
            if hasattr(response, 'usage') and response.usage:
                self.log_token_usage(
                    action="generate_optimization",
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    model="claude-sonnet-4-20250514"
                )

            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
        except Exception as e:
            self.last_error = str(e)
            return fallback_res

    async def analyze_security_threats(self, log_summary: str) -> str:
        """Analyze security logs (ssh auth, fail2ban) and generate an executive report."""
        if not self.enabled:
            return "AI Brain tidak aktif. Set ANTHROPIC_API_KEY untuk laporan analisis keamanan pintar."

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
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
            if hasattr(response, 'usage') and response.usage:
                self.log_token_usage(
                    action="analyze_security_threats",
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    model="claude-sonnet-4-20250514"
                )

            return response.content[0].text
        except Exception as e:
            self.last_error = str(e)
            return f"Gagal menganalisis keamanan: {e}"
