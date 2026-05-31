"""
SyamAdminBot — Telegram bot interface for server management.
All commands flow through here → modules → executor.
"""

import asyncio
import logging
import os
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
        await update.message.reply_text(
            "⚠️ *Provisioning LEMP Stack*\n\n"
            "Ini akan menginstall:\n"
            "• Nginx\n• MySQL 8\n• PHP 8.3 + extensions\n• Composer\n• Certbot\n\n"
            "Kirim `/confirm provision` untuk melanjutkan.",
            parse_mode="Markdown",
        )
        self._pending_confirmations[self.admin_id] = {
            "action": "provision",
            "expires": datetime.now().timestamp() + 120,
        }

    async def cmd_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return

        pending = self._pending_confirmations.get(self.admin_id)
        if not pending or pending["expires"] < datetime.now().timestamp():
            await update.message.reply_text("❌ Tidak ada aksi yang menunggu konfirmasi.")
            return

        action = pending["action"]
        del self._pending_confirmations[self.admin_id]

        if action == "provision":
            await update.message.reply_text("🚀 Memulai provisioning... (ini memakan waktu 5-10 menit)")
            asyncio.create_task(self.modules["provisioner"].install_lemp())

    async def cmd_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []

        if not args:
            await update.message.reply_text(
                "Penggunaan:\n"
                "`/site add domain.com` — tambah site\n"
                "`/site list` — list semua site\n"
                "`/site ssl domain.com` — aktifkan SSL\n"
                "`/site remove domain.com` — hapus site",
                parse_mode="Markdown",
            )
            return

        action = args[0].lower()
        sm = self.modules["site_manager"]

        if action == "add" and len(args) >= 2:
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
            result = await sm.remove_site(domain)
            await update.message.reply_text(result, parse_mode="Markdown")

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
            result = await fm.deny_port(args[1])
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
            await msg.edit_text(
                f"⚠️ *Konfirmasi Diperlukan*\n\n"
                f"Intent: {result['intent']}\n"
                f"Aksi: `{result['module']}.{result['action']}`\n\n"
                f"{result['message']}\n\n"
                f"Kirim `/confirm ai` untuk melanjutkan.",
                parse_mode="Markdown",
            )
            self._pending_confirmations[self.admin_id] = {
                "action": "ai",
                "result": result,
                "expires": datetime.now().timestamp() + 120,
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
        """Handle free-text messages (route to AI brain)."""
        if not await self._guard(update):
            return

        # Check for pending confirmation
        pending = self._pending_confirmations.get(self.admin_id)
        if pending and pending["expires"] > datetime.now().timestamp():
            user_text = update.message.text.lower().strip()
            if user_text in ("ya", "yes", "ok", "lanjut", "confirm"):
                if pending["action"] == "ai":
                    response = await self._execute_ai_action(pending["result"])
                    del self._pending_confirmations[self.admin_id]
                    await update.message.reply_text(response, parse_mode="Markdown")
                    return

        # Otherwise, treat as AI command
        context.args = update.message.text.split()
        await self.cmd_ai(update, context)

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

        # Free-text handler (last)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Set bot commands menu
        await app.bot.set_my_commands([
            BotCommand("status", "Status server"),
            BotCommand("services", "Status layanan"),
            BotCommand("site", "Manage sites"),
            BotCommand("security", "Security audit"),
            BotCommand("firewall", "Status firewall"),
            BotCommand("backup", "Backup management"),
            BotCommand("logs", "Lihat log"),
            BotCommand("ai", "AI command"),
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
