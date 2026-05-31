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

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = None
        self.enabled = bool(api_key)

        if not self.enabled:
            logger.warning("AI Brain disabled — no ANTHROPIC_API_KEY configured")

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
            return response.content[0].text
        except Exception as e:
            return f"Gagal menganalisis log: {e}"
