"""
SyamAdminBot — Telegram bot interface for server management.
All commands flow through here → modules → executor.
"""

import asyncio
import logging
import os
import secrets
import re
from datetime import datetime
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logger = logging.getLogger("syamadmin.bot")

HELP_TEXT = """
🤖 *SyamAdmin — AI Sysadmin Agent*

*Perintah Utama:*
`/status` — Status server (CPU, RAM, Disk)
`/services` — Status semua managed services
`/provision` — Setup LEMP stack dari awal
`/logs [service]` — Lihat log terbaru

*Site Management:*
`/site add domain.com` — Tambah site baru
`/site list` — List semua site
`/site ssl domain.com` — Aktifkan SSL
`/site remove domain.com` — Hapus site

*Security & Firewall:*
`/security` — Jalankan security audit
`/harden` — Hardening SSH + Fail2Ban
`/firewall` — Status firewall
`/fw allow 3306` — Buka port
`/fw deny 3306` — Tutup port

*Backup:*
`/backup` — Full backup (DB + files)
`/backup db` — Backup databases saja
`/backup list` — List backup tersedia

*AI Commands:*
`/ai [perintah bebas]` — Perintah natural language
Contoh: `/ai restart nginx dan cek errorlog`

*System:*
`/audit` — Lihat audit log
`/help` — Bantuan ini
"""


class SyamAdminBot:
    """Telegram bot for SyamAdmin agent."""

    def __init__(self, token: str, admin_id: int, modules: dict, server_name: str = "VPS"):
        self.token = token
        self.admin_id = admin_id
        self.modules = modules
        self.server_name = server_name
        self._app: Application | None = None
        self._pending_confirmations: dict = {}
        self._wizard_states: dict = {}

    def _generate_otp(self) -> str:
        """Generate a cryptographically secure 4-digit numeric OTP."""
        return str(secrets.randbelow(9000) + 1000)

    def _is_admin(self, update: Update) -> bool:
        return update.effective_user and update.effective_user.id == self.admin_id

    async def _guard(self, update: Update) -> bool:
        """Check if user is authorized admin."""
        if not self._is_admin(update):
            await update.message.reply_text(
                "⛔ Unauthorized. Hanya admin yang bisa menggunakan bot ini."
            )
            logger.warning(
                f"Unauthorized access attempt from user {update.effective_user.id} "
                f"({update.effective_user.username})"
            )
            return False
        return True

    # ---- Command Handlers ----

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        await update.message.reply_text(
            f"🤖 *SyamAdmin Agent*\n\n"
            f"Server: `{self.server_name}`\n"
            f"Status: 🟢 Online\n\n"
            f"Kirim /help untuk daftar perintah.",
            parse_mode="Markdown",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        msg = await update.message.reply_text("⏳ Collecting metrics...")
        report = await self.modules["monitor"].get_status_report()
        await msg.edit_text(report, parse_mode="Markdown")

    async def cmd_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        msg = await update.message.reply_text("⏳ Checking services...")
        report = await self.modules["monitor"].get_services_status()
        await msg.edit_text(report, parse_mode="Markdown")

    async def cmd_provision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        otp = self._generate_otp()
        await update.message.reply_text(
            "⚠️ *Provisioning LEMP Stack*\n\n"
            "Ini akan menginstall:\n"
            "• Nginx\n• MySQL 8\n• PHP 8.3 + extensions\n• Composer\n• Certbot\n\n"
            f"Kirim `/confirm {otp}` untuk mengeksekusi (berlaku 60 detik).",
            parse_mode="Markdown",
        )
        self._pending_confirmations[self.admin_id] = {
            "action": "provision",
            "otp": otp,
            "expires": datetime.now().timestamp() + 60,
        }

    async def cmd_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return

        args = context.args or []
        if not args:
            await update.message.reply_text("❌ Format salah. Gunakan: `/confirm <KODE_OTP>`")
            return

        user_otp = args[0].strip()
        pending = self._pending_confirmations.get(self.admin_id)

        if not pending or pending["expires"] < datetime.now().timestamp():
            await update.message.reply_text("❌ Tidak ada aksi yang menunggu konfirmasi atau kode telah kedaluwarsa.")
            return

        if user_otp != pending.get("otp"):
            await update.message.reply_text("❌ Kode OTP konfirmasi salah. Silakan coba lagi.")
            return

        # OTP is correct. Proceed to execute.
        del self._pending_confirmations[self.admin_id]
        await self._execute_confirmed_action(update, pending)

    async def cmd_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []

        if not args:
            await update.message.reply_text(
                "Penggunaan:\n"
                "`/site wizard` — wizard interaktif pembuatan situs\n"
                "`/site add domain.com` — tambah site\n"
                "`/site list` — list semua site\n"
                "`/site ssl domain.com` — aktifkan SSL\n"
                "`/site remove domain.com` — hapus site",
                parse_mode="Markdown",
            )
            return

        action = args[0].lower()
        sm = self.modules["site_manager"]

        if action == "wizard":
            await self.cmd_site_wizard(update, context)

        elif action == "add" and len(args) >= 2:
            domain = args[1]
            framework = args[2] if len(args) > 2 else "default"
            result = await sm.add_site(domain, framework=framework)
            await update.message.reply_text(result, parse_mode="Markdown")

        elif action == "list":
            result = await sm.list_sites()
            await update.message.reply_text(result, parse_mode="Markdown")

        elif action == "ssl" and len(args) >= 2:
            domain = args[1]
            await update.message.reply_text(f"🔒 Setting up SSL for `{domain}`...", parse_mode="Markdown")
            result = await sm.enable_ssl(domain)
            await update.message.reply_text(result, parse_mode="Markdown")

        elif action == "remove" and len(args) >= 2:
            domain = args[1]
            otp = self._generate_otp()
            await update.message.reply_text(
                f"🗑️ *Konfirmasi Hapus Site `{domain}`*\n\n"
                f"Kirim `/confirm {otp}` untuk mengeksekusi (berlaku 60 detik).",
                parse_mode="Markdown",
            )
            self._pending_confirmations[self.admin_id] = {
                "action": "remove_site",
                "domain": domain,
                "otp": otp,
                "expires": datetime.now().timestamp() + 60,
            }

        else:
            await update.message.reply_text("❌ Perintah site tidak valid. Kirim `/site` untuk bantuan.", parse_mode="Markdown")

    async def cmd_security(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        msg = await update.message.reply_text("🔍 Running security audit...")
        result = await self.modules["security"].audit()
        await msg.edit_text(result, parse_mode="Markdown")

    async def cmd_harden(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        await update.message.reply_text("🔐 Starting hardening process...")
        r1 = await self.modules["security"].harden_ssh()
        r2 = await self.modules["security"].setup_fail2ban()
        r3 = await self.modules["firewall"].setup_defaults()
        r4 = await self.modules["security"].setup_auto_updates()

        summary = f"🔐 *Hardening Complete*\n\n{r1}\n\n{r2}\n\n{r3}\n\n{r4}"
        # Truncate if too long for Telegram
        if len(summary) > 4000:
            summary = summary[:3900] + "\n\n_(truncated)_"
        await update.message.reply_text(summary, parse_mode="Markdown")

    async def cmd_firewall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        result = await self.modules["firewall"].status()
        await update.message.reply_text(result, parse_mode="Markdown")

    async def cmd_fw(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Quick firewall commands: /fw allow 3306, /fw deny 8080"""
        if not await self._guard(update):
            return
        args = context.args or []
        fm = self.modules["firewall"]

        if len(args) < 2:
            await update.message.reply_text(
                "Penggunaan:\n`/fw allow 3306` — buka port\n`/fw deny 3306` — tutup port\n`/fw rules` — list rules",
                parse_mode="Markdown",
            )
            return

        action = args[0].lower()
        if action == "allow":
            result = await fm.allow_port(args[1])
        elif action == "deny":
            port = args[1]
            ssh_port = os.environ.get("SSH_PORT", "22")
            if port == ssh_port or port == "22":
                otp = self._generate_otp()
                await update.message.reply_text(
                    f"⚠️ *Peringatan Keamanan Port SSH ({port})*\n\n"
                    "Anda akan menutup akses port SSH! Tindakan ini dapat mengunci akses Anda ke server.\n\n"
                    f"Kirim `/confirm {otp}` untuk mengeksekusi (berlaku 60 detik).",
                    parse_mode="Markdown",
                )
                self._pending_confirmations[self.admin_id] = {
                    "action": "deny_ssh",
                    "port": port,
                    "otp": otp,
                    "expires": datetime.now().timestamp() + 60,
                }
                return
            result = await fm.deny_port(port)
        elif action == "rules":
            result = await fm.list_rules()
        else:
            result = "❌ Gunakan `allow`, `deny`, atau `rules`."

        await update.message.reply_text(result, parse_mode="Markdown")

    async def cmd_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []
        bm = self.modules["backup"]

        if not args:
            await update.message.reply_text("💾 Starting full backup...")
            result = await bm.backup_all()
        elif args[0] == "db":
            result = await bm.backup_db()
        elif args[0] == "files":
            result = await bm.backup_files()
        elif args[0] == "list":
            result = await bm.list_backups()
        else:
            result = "Penggunaan: `/backup` | `/backup db` | `/backup files` | `/backup list`"

        await update.message.reply_text(result, parse_mode="Markdown")

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []
        service = args[0] if args else "syslog"

        log_map = {
            "nginx": "/var/log/nginx/error.log",
            "mysql": "/var/log/mysql/error.log",
            "auth": "/var/log/auth.log",
            "syslog": "/var/log/syslog",
            "fail2ban": "/var/log/fail2ban.log",
        }

        log_path = log_map.get(service, f"/var/log/{service}.log")
        r = await self.modules["executor"].run(
            f"tail -30 {log_path} 2>/dev/null || echo 'Log file not found: {log_path}'",
            module="bot",
        )
        await update.message.reply_text(
            f"📋 *Log: {service}*\n```\n{r['stdout'][:3500]}\n```",
            parse_mode="Markdown",
        )

    async def cmd_audit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        entries = await self.modules["executor"].get_recent_audit(limit=15)
        if not entries:
            await update.message.reply_text("📭 Belum ada audit log.")
            return

        lines = ["📋 *Recent Audit Log*\n"]
        for e in entries:
            icon = "✅" if e["status"] == "success" else "❌"
            lines.append(f"{icon} `{e['timestamp']}` [{e['module']}] {e['action'][:60]}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Natural language command processing via AI Brain."""
        if not await self._guard(update):
            return

        user_msg = " ".join(context.args) if context.args else ""
        if not user_msg:
            await update.message.reply_text(
                "💡 Contoh penggunaan:\n"
                "`/ai restart nginx`\n"
                "`/ai cek kenapa disk penuh`\n"
                "`/ai tambah site example.com dengan laravel`\n"
                "`/ai install redis`",
                parse_mode="Markdown",
            )
            return

        # Check if it is an Auto-Repair request: e.g. "perbaiki nginx"
        match = re.match(r"^(?:perbaiki|repair)\s+([a-zA-Z0-9.\-_]+)$", user_msg.lower().strip())
        if match:
            svc = match.group(1)
            log_paths = {
                "nginx": "/var/log/nginx/error.log",
                "mysql": "/var/log/mysql/error.log",
                "fail2ban": "/var/log/fail2ban.log",
            }
            path = log_paths.get(svc, f"/var/log/{svc}.log")
            log_res = await self.modules["executor"].run(
                f"tail -n 25 {path} 2>/dev/null || journalctl -u {svc} -n 25 --no-pager",
                module="bot", check=False
            )
            log_content = log_res["stdout"].strip() or "No recent logs found."
            
            msg = await update.message.reply_text("🧠 Menganalisis log dan menyiapkan perbaikan...")
            diag = await self.modules["brain"].diagnose_crash(svc, log_content)
            
            otp = self._generate_otp()
            await msg.edit_text(
                f"⚠️ *Otorisasi Perbaikan Otomatis ({svc})*\n\n"
                f"• *Penyebab*: {diag.get('cause')}\n"
                f"• *Solusi*: {diag.get('solution')}\n"
                f"• *Perintah Perbaikan*: `{diag.get('repair_command')}`\n"
                f"• *Risiko*: {diag.get('risk')}\n\n"
                f"Kirim `/confirm {otp}` atau cukup balas dengan `{otp}` untuk melanjutkan.",
                parse_mode="Markdown",
            )
            self._pending_confirmations[self.admin_id] = {
                "action": "repair_service",
                "service": svc,
                "command": diag.get("repair_command"),
                "otp": otp,
                "expires": datetime.now().timestamp() + 60,
            }
            return

        msg = await update.message.reply_text("🧠 Processing...")

        # Get current server context for AI
        metrics = await self.modules["monitor"].collect_metrics()
        context_str = (
            f"CPU: {metrics['cpu_percent']}%, RAM: {metrics['ram_percent']}%, "
            f"Disk: {metrics['disk_percent']}%, Load: {metrics['load_1']}, "
            f"Uptime: {metrics['uptime_str']}"
        )

        # Process through AI Brain
        result = await self.modules["brain"].process_command(user_msg, context_str)

        if result["action"] == "clarify":
            await msg.edit_text(result["message"], parse_mode="Markdown")
            return

        if result.get("confirmation_needed"):
            otp = self._generate_otp()
            await msg.edit_text(
                f"⚠️ *Konfirmasi Diperlukan*\n\n"
                f"Intent: {result['intent']}\n"
                f"Aksi: `{result['module']}.{result['action']}`\n\n"
                f"{result['message']}\n\n"
                f"Kirim `/confirm {otp}` untuk mengeksekusi (berlaku 60 detik).",
                parse_mode="Markdown",
            )
            self._pending_confirmations[self.admin_id] = {
                "action": "ai",
                "result": result,
                "otp": otp,
                "expires": datetime.now().timestamp() + 60,
            }
            return

        # Execute the parsed action
        response = await self._execute_ai_action(result)
        await msg.edit_text(response, parse_mode="Markdown")

    async def _execute_ai_action(self, parsed: dict) -> str:
        """Execute an AI-parsed action through the appropriate module."""
        module_name = parsed.get("module", "")
        action = parsed.get("action", "")
        params = parsed.get("params", {})

        try:
            module = self.modules.get(module_name)
            if not module:
                return f"❌ Modul `{module_name}` tidak ditemukan."

            # Route to the correct method
            method = getattr(module, action, None)
            if method and callable(method):
                result = await method(**params) if params else await method()
                return result if isinstance(result, str) else str(result)

            # Special cases
            if module_name == "executor" and action == "service_restart":
                svc = params.get("service", "")
                r = await self.modules["executor"].service_action(svc, "restart")
                return f"{'✅' if r['success'] else '❌'} Service `{svc}` restart: {r['stdout'] or r['stderr']}"

            if module_name == "executor" and action == "run_command":
                cmd = params.get("command", "")
                r = await self.modules["executor"].run(cmd, module="ai_command")
                return f"```\n{r['stdout'][:3000]}\n```" if r["success"] else f"❌ Error:\n```\n{r['stderr'][:1000]}\n```"

            return parsed.get("message", f"Aksi `{action}` pada modul `{module_name}` belum diimplementasi.")

        except Exception as e:
            logger.error(f"AI action execution error: {e}", exc_info=True)
            return f"❌ Error executing action: {e}"

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free-text messages (route to AI brain or wizard)."""
        if not await self._guard(update):
            return

        # 1. Check if user is currently inside the interactive site wizard
        wizard = self._wizard_states.get(self.admin_id)
        if wizard:
            user_text = update.message.text.strip()
            state = wizard["state"]

            if state == "DOMAIN":
                domain_regex = r"^[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+$"
                if not re.match(domain_regex, user_text):
                    await update.message.reply_text(
                        "❌ Format domain tidak valid. Silakan masukkan domain yang benar (misal: `situsku.com`):"
                    )
                    return
                
                wizard["domain"] = user_text.lower()
                wizard["state"] = "TYPE"
                await update.message.reply_text(
                    f"🌐 *Domain terpilih:* `{wizard['domain']}`\n\n"
                    f"👉 *Langkah 2:* Pilih jenis/framework website Anda. Ketik salah satu:\n"
                    f"• `default` (HTML/PHP biasa)\n"
                    f"• `wordpress`\n"
                    f"• `laravel`"
                )
                return

            elif state == "TYPE":
                framework = user_text.lower()
                if framework not in ("default", "wordpress", "laravel"):
                    await update.message.reply_text(
                        "❌ Jenis framework tidak dikenal. Silakan ketik salah satu dari: `default`, `wordpress`, atau `laravel`:"
                    )
                    return
                
                wizard["framework"] = framework
                wizard["state"] = "DB"
                await update.message.reply_text(
                    f"🚀 *Framework terpilih:* `{framework}`\n\n"
                    f"👉 *Langkah 3:* Apakah Anda membutuhkan database MySQL untuk situs ini?\n"
                    f"Ketik *ya* atau *tidak*:"
                )
                return

            elif state == "DB":
                choice = user_text.lower()
                if choice not in ("ya", "tidak"):
                    await update.message.reply_text(
                        "❌ Pilihan tidak valid. Silakan ketik *ya* atau *tidak*:"
                    )
                    return
                
                need_db = choice == "ya"
                domain = wizard["domain"]
                framework = wizard["framework"]
                
                # Remove from wizard states before prompting confirmation
                del self._wizard_states[self.admin_id]
                
                otp = self._generate_otp()
                self._pending_confirmations[self.admin_id] = {
                    "action": "wizard_provision",
                    "domain": domain,
                    "framework": framework,
                    "db": need_db,
                    "otp": otp,
                    "expires": datetime.now().timestamp() + 120,
                }
                
                await update.message.reply_text(
                    f"📝 *Ringkasan Konfigurasi Website*\n\n"
                    f"• *Domain*: `{domain}`\n"
                    f"• *Framework/Platform*: `{framework}`\n"
                    f"• *Buat Database MySQL*: `{'Ya' if need_db else 'Tidak'}`\n\n"
                    f"⚠️ *Peringatan*: Proses ini akan mengubah konfigurasi Nginx dan Firewall.\n"
                    f"Kirim `/confirm {otp}` atau cukup balas dengan `{otp}` untuk mengeksekusi.",
                    parse_mode="Markdown"
                )
                return

        # 2. Check for pending OTP confirmation
        pending = self._pending_confirmations.get(self.admin_id)
        if pending and pending["expires"] > datetime.now().timestamp():
            user_text = update.message.text.strip()
            # Support both the raw OTP code or explicit confirm commands
            if user_text == pending.get("otp"):
                del self._pending_confirmations[self.admin_id]
                await self._execute_confirmed_action(update, pending)
                return

        # 3. Otherwise, treat as AI command
        context.args = update.message.text.split()
        await self.cmd_ai(update, context)

    async def cmd_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display real-time Claude API token utilization statistics and costs."""
        if not await self._guard(update):
            return
        
        msg = await update.message.reply_text("⏳ Mengambil data penggunaan token...")
        stats = self.modules["brain"].get_token_statistics()
        
        report = (
            f"📊 *Statistik Penggunaan Claude API*\n\n"
            f"• *Status API*: {stats['api_status']}\n"
            f"• *Total Pemanggilan*: `{stats['calls_count']}`\n"
            f"• *Token Input*: `{stats['total_input']:,}`\n"
            f"• *Token Output*: `{stats['total_output']:,}`\n"
            f"• *Total Token*: `{stats['total_tokens']:,}`\n\n"
            f"💰 *Estimasi Biaya Akumulatif*:\n"
            f"• USD: `${stats['cost_usd']:.5f}`\n"
            f"• IDR: `Rp {stats['cost_idr']:,.2f}`\n\n"
            f"_Note: Estimasi dihitung berdasarkan tarif resmi Claude 3.5 Sonnet._"
        )
        await msg.edit_text(report, parse_mode="Markdown")

    async def cmd_cron(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Natural language scheduling via AI."""
        if not await self._guard(update):
            return
            
        user_msg = " ".join(context.args) if context.args else ""
        if not user_msg:
            await update.message.reply_text(
                "💡 Contoh penggunaan:\n"
                "`/cron backup db setiap jam 3 pagi`\n"
                "`/cron audit keamanan setiap hari minggu jam 11 malam`\n"
                "`/cron scan rootkit tiap jam 12 malam`",
                parse_mode="Markdown"
            )
            return
            
        msg = await update.message.reply_text("🧠 Menganalisis waktu penjadwalannya...")
        res = await self.modules["brain"].parse_cron_instruction(user_msg)
        
        if not res.get("success"):
            await msg.edit_text(res.get("message", "❌ Gagal memahami waktu penjadwalan."), parse_mode="Markdown")
            return
            
        otp = self._generate_otp()
        await msg.edit_text(
            f"📅 *Konfirmasi Penjadwalan Otomatis (AI)*\n\n"
            f"• *Tugas*: `{res['command']}`\n"
            f"• *Jadwal*: {res['readable_summary']}\n"
            f"• *Ekspresi Cron*: `{res['cron_expression']}`\n\n"
            f"Kirim `/confirm {otp}` atau cukup balas dengan `{otp}` untuk melanjutkan.",
            parse_mode="Markdown",
        )
        self._pending_confirmations[self.admin_id] = {
            "action": "add_cron",
            "cron_expression": res["cron_expression"],
            "command": res["command"],
            "readable_summary": res["readable_summary"],
            "otp": otp,
            "expires": datetime.now().timestamp() + 60,
        }

    async def cmd_optimize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Analyze server performance history and recommend dynamic optimizations."""
        if not await self._guard(update):
            return
            
        msg = await update.message.reply_text("📊 Membaca tren historis dan menyusun rekomendasi...")
        
        # 1. Fetch metrics summary
        summary = await self.modules["monitor"].get_historical_summary(days=7)
        
        # 2. Call brain to advise
        res = await self.modules["brain"].generate_optimization_report(summary)
        
        report_text = f"💡 *Analisis Kinerja & Rekomendasi AI*\n\n{res.get('report')}"
        
        if res.get("has_recommendation"):
            otp = self._generate_otp()
            report_text += (
                f"\n\n⚙️ *Tindakan Optimasi Tersedia ({res.get('target_service')})*:\n"
                f"• *Perintah*: `{res.get('optimization_command')}`\n"
                f"• *Risiko*: {res.get('risk')}\n\n"
                f"Kirim `/confirm {otp}` atau balas dengan `{otp}` untuk menerapkan optimasi ini."
            )
            self._pending_confirmations[self.admin_id] = {
                "action": "optimize_system",
                "service": res.get("target_service"),
                "command": res.get("optimization_command"),
                "otp": otp,
                "expires": datetime.now().timestamp() + 60,
            }
            
        await msg.edit_text(report_text, parse_mode="Markdown")

    async def cmd_site_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Initiate the step-by-step interactive site setup wizard."""
        if not await self._guard(update):
            return
        
        self._wizard_states[self.admin_id] = {"state": "DOMAIN"}
        await update.message.reply_text(
            "🧙‍♂️ *Interactive Site Provisioning Wizard*\n\n"
            "Mari siapkan website baru Anda langkah demi langkah.\n\n"
            "👉 *Langkah 1:* Silakan masukkan *nama domain* untuk website Anda (misal: `example.com`):",
            parse_mode="Markdown",
        )

    async def cmd_security_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display an AI security log scanner intelligence report."""
        if not await self._guard(update):
            return
        msg = await update.message.reply_text("⏳ Menganalisis log keamanan server...")
        report = await self.modules["security"].scan_auth_logs(brain=self.modules["brain"])
        await msg.edit_text(report, parse_mode="Markdown")

    async def cmd_harden_ssh_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Request shifting the SSH port to a non-standard port with dynamic OTP verification."""
        if not await self._guard(update):
            return
        args = context.args or []
        if not args:
            await update.message.reply_text("❌ Format salah. Gunakan: `/harden_ssh_port <PORT_BARU>` (rentang 1024 - 65535)")
            return
        try:
            new_port = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Port harus berupa angka numerik valid.")
            return
            
        otp = self._generate_otp()
        await update.message.reply_text(
            f"⚠️ *Konfirmasi Perubahan Port SSH* 🔐\n\n"
            f"Anda akan mengubah port SSH dari `{self.modules['security'].ssh_port}` menjadi `{new_port}`.\n"
            f"Tindakan ini sangat kritis dan membutuhkan otorisasi keamanan!\n\n"
            f"Kirim `/confirm {otp}` atau cukup balas dengan `{otp}` untuk mengeksekusi.",
            parse_mode="Markdown"
        )
        
        self._pending_confirmations[self.admin_id] = {
            "action": "change_ssh_port",
            "new_port": new_port,
            "otp": otp,
            "expires": datetime.now().timestamp() + 120,
        }

    async def _execute_confirmed_action(self, update: Update, pending: dict):
        """Common executor for all confirmed actions via OTP validation."""
        action = pending["action"]
        
        if action == "provision":
            await update.message.reply_text("🚀 Memulai provisioning... (ini memakan waktu 5-10 menit)")
            asyncio.create_task(self.modules["provisioner"].install_lemp())

        elif action == "remove_site":
            domain = pending["domain"]
            await update.message.reply_text(f"🗑️ Menghapus site `{domain}`...")
            result = await self.modules["site_manager"].remove_site(domain)
            await update.message.reply_text(result, parse_mode="Markdown")

        elif action == "deny_ssh":
            port = pending["port"]
            await update.message.reply_text(f"🛑 Menutup port SSH `{port}`...")
            result = await self.modules["firewall"].deny_port(port)
            await update.message.reply_text(result, parse_mode="Markdown")

        elif action == "ai":
            await update.message.reply_text("⚙️ Mengeksekusi aksi AI yang dikonfirmasi...")
            response = await self._execute_ai_action(pending["result"])
            await update.message.reply_text(response, parse_mode="Markdown")

        elif action == "repair_service":
            cmd = pending["command"]
            svc = pending["service"]
            await update.message.reply_text(f"🔧 Menjalankan perbaikan otomatis untuk `{svc}`...")
            result = await self.modules["executor"].run(cmd, module="auto_repair")
            if result["success"]:
                status = await self.modules["executor"].run(f"systemctl is-active {svc}", module="auto_repair", check=False)
                active_str = "🟢 Aktif" if status["stdout"].strip() == "active" else "🔴 Masih Gagal"
                await update.message.reply_text(
                    f"✅ *Perbaikan Selesai!*\n\n"
                    f"Output:\n```\n{result['stdout'][:2000]}\n```\n"
                    f"Status Layanan: *{active_str}*",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ *Perbaikan Gagal!*\n\n"
                    f"Error:\n```\n{result['stderr'][:2000]}\n```",
                    parse_mode="Markdown"
                )

        elif action == "optimize_system":
            cmd = pending["command"]
            svc = pending["service"]
            await update.message.reply_text(f"⚙️ Menerapkan optimasi sistem untuk `{svc}`...", parse_mode="Markdown")
            result = await self.modules["executor"].run(cmd, module="optimization")
            if result["success"]:
                await update.message.reply_text(
                    f"✅ *Optimasi Berhasil Diterapkan!*\n\n"
                    f"Output:\n```\n{result['stdout'][:2000]}\n```",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ *Gagal menerapkan optimasi!*\n\n"
                    f"Error:\n```\n{result['stderr'][:2000]}\n```",
                    parse_mode="Markdown"
                )

        elif action == "add_cron":
            cron_expr = pending["cron_expression"]
            cmd = pending["command"]
            summary = pending["readable_summary"]
            await update.message.reply_text(f"⏳ Menjadwalkan `{cmd}`...")
            result = await self.modules["executor"].add_cron_job(cron_expr, cmd)
            if result["success"]:
                await update.message.reply_text(
                    f"✅ *Penjadwalan Berhasil!* 📅\n\n"
                    f"• *Tugas*: `{cmd}`\n"
                    f"• *Jadwal*: {summary}\n"
                    f"• *Cron Expression*: `{cron_expr}`",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ *Gagal menjadwalkan tugas!*\n\n"
                    f"Error:\n```\n{result['stderr']}\n```",
                    parse_mode="Markdown"
                )

        elif action == "wizard_provision":
            domain = pending["domain"]
            framework = pending["framework"]
            db = pending["db"]
            
            await update.message.reply_text(f"⏳ *Memulai instalasi website `{domain}`...*", parse_mode="Markdown")
            
            sm = self.modules["site_manager"]
            site_result = await sm.add_site(domain, framework=framework)
            
            db_info = ""
            if db:
                clean_domain = re.sub(r"[^a-zA-Z0-9]", "", domain.split(".")[0])[:12]
                db_name = f"db_{clean_domain}_{secrets.token_hex(2)}"
                db_user = f"usr_{clean_domain}"
                db_pass = secrets.token_urlsafe(10)
                
                await update.message.reply_text(f"🗄️ *Membuat database `{db_name}`...*", parse_mode="Markdown")
                
                db_commands = [
                    f"mysql -e \"CREATE DATABASE IF NOT EXISTS `{db_name}`;\"",
                    f"mysql -e \"CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_pass}';\"",
                    f"mysql -e \"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'localhost';\"",
                    f"mysql -e \"FLUSH PRIVILEGES;\""
                ]
                
                db_success = True
                db_err = ""
                for cmd in db_commands:
                    res = await self.modules["executor"].run(cmd, module="wizard_db", check=False)
                    if not res["success"]:
                        db_success = False
                        db_err = res["stderr"]
                        break
                
                if db_success:
                    db_info = (
                        f"🗄️ *Database MySQL Berhasil Dibuat!*\n"
                        f"• *Database Name*: `{db_name}`\n"
                        f"• *Database User*: `{db_user}`\n"
                        f"• *Database Password*: `{db_pass}`\n\n"
                    )
                else:
                    db_info = f"⚠️ *Pembuatan database gagal*:\n```\n{db_err[:300]}\n```\n\n"
            
            await update.message.reply_text(f"🔒 *Menyiapkan SSL Let's Encrypt untuk `{domain}`...*", parse_mode="Markdown")
            ssl_result = await sm.enable_ssl(domain)
            
            final_report = (
                f"🎉 *Instalasi Website Selesai!* 🎉\n\n"
                f"🌐 *Domain*: `{domain}`\n"
                f"{db_info}"
                f"🔒 *SSL Let's Encrypt Status*:\n{ssl_result}\n\n"
                f"Situs Anda sekarang telah dikonfigurasi dan aktif!"
            )
            
            if len(final_report) > 4000:
                final_report = final_report[:3900] + "\n\n_(truncated)_"
                
            await update.message.reply_text(final_report, parse_mode="Markdown")

        elif action == "change_ssh_port":
            new_port = pending["new_port"]
            await update.message.reply_text(f"🔐 *Mengubah port SSH ke `{new_port}`...*", parse_mode="Markdown")
            result = await self.modules["security"].change_ssh_port(new_port)
            await update.message.reply_text(result, parse_mode="Markdown")

    async def run(self):
        """Start the Telegram bot."""
        logger.info("Starting Telegram bot...")

        self._app = Application.builder().token(self.token).build()
        app = self._app

        # Register command handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("services", self.cmd_services))
        app.add_handler(CommandHandler("provision", self.cmd_provision))
        app.add_handler(CommandHandler("confirm", self.cmd_confirm))
        app.add_handler(CommandHandler("site", self.cmd_site))
        app.add_handler(CommandHandler("security", self.cmd_security))
        app.add_handler(CommandHandler("harden", self.cmd_harden))
        app.add_handler(CommandHandler("firewall", self.cmd_firewall))
        app.add_handler(CommandHandler("fw", self.cmd_fw))
        app.add_handler(CommandHandler("backup", self.cmd_backup))
        app.add_handler(CommandHandler("logs", self.cmd_logs))
        app.add_handler(CommandHandler("audit", self.cmd_audit))
        app.add_handler(CommandHandler("ai", self.cmd_ai))
        app.add_handler(CommandHandler("token", self.cmd_token))
        app.add_handler(CommandHandler("cron", self.cmd_cron))
        app.add_handler(CommandHandler("optimize", self.cmd_optimize))
        app.add_handler(CommandHandler("security_report", self.cmd_security_report))
        app.add_handler(CommandHandler("harden_ssh_port", self.cmd_harden_ssh_port))

        # Free-text handler (last)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Set bot commands menu
        await app.bot.set_my_commands([
            BotCommand("status", "Status server"),
            BotCommand("services", "Status layanan"),
            BotCommand("site", "Manage sites"),
            BotCommand("security", "Security audit"),
            BotCommand("security_report", "Laporan Keamanan AI"),
            BotCommand("harden_ssh_port", "Ubah Port SSH Aman"),
            BotCommand("firewall", "Status firewall"),
            BotCommand("backup", "Backup management"),
            BotCommand("logs", "Lihat log"),
            BotCommand("ai", "AI command"),
            BotCommand("token", "Statistik Token AI"),
            BotCommand("cron", "AI Task Scheduler"),
            BotCommand("optimize", "AI Resource Optimizer"),
            BotCommand("help", "Bantuan"),
        ])

        logger.info("Telegram bot started, polling for messages...")

        # Initialize and start polling
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # Keep running until cancelled
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("Bot shutting down...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
