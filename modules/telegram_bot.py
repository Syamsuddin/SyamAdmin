"""
SyamAdminBot — Telegram bot interface for server management.
All commands flow through here → modules → executor.
"""

import asyncio
import logging
import os
import secrets
import re
import time
from datetime import datetime
from telegram import Update, BotCommand
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from modules.monitor import MANAGED_SERVICES
from modules.brain import AVAILABLE_MODELS

logger = logging.getLogger("syamadmin.bot")

# Peta alias: nama-aksi-yang-diajarkan-ke-AI -> nama-method-nyata di modul.
# Mencegah kegagalan diam-diam saat AI memakai nama ramah yang berbeda dari method.
ACTION_ALIASES = {
    "monitor": {
        "status": "get_status_report",
        "services": "get_services_status",
        "disk_usage": "get_disk_report",
        "top_processes": "get_top_processes",
        "connections": "get_connections",
    },
    "firewall": {
        "reset": "setup_defaults",
    },
    "site_manager": {
        "disable_site": "disable_site",
    },
    "provisioner": {
        "setup_composer": "setup_composer",
    },
    "backup": {
        "restore": "restore",
    },
}

# Kata afirmatif yang diterima sebagai konfirmasi untuk aksi non-destruktif
AFFIRMATIVE_WORDS = {"ya", "iya", "ok", "oke", "yes", "y", "lanjut", "setuju", "gas"}

# Aksi destruktif yang WAJIB menggunakan OTP (kata afirmatif tidak cukup)
DESTRUCTIVE_ACTIONS = {
    "provision", "remove_site", "deny_ssh", "change_ssh_port",
    "restore", "repair_service", "wizard_provision",
}

# Aksi read-only (allowlist) — dipakai gating OTP orchestrator. Step plan yang
# TIDAK ada di sini dianggap mengubah state → seluruh plan wajib OTP.
SAFE_READONLY_ACTIONS = {
    "status", "services", "top_processes", "disk_usage", "connections",
    "list_rules", "list_sites", "list_backups", "audit", "check_updates",
    "scan_rootkit", "get_status_report", "get_services_status",
    "get_disk_report", "get_top_processes", "get_connections",
}

HELP_TEXT = """
🤖 *SyamAdmin — AI Sysadmin Agent*

*Server & Monitoring:*
`/status` — Status server (CPU, RAM, Disk)
`/services` — Status semua managed services
`/logs [service]` — Lihat log terbaru
`/audit` — Lihat audit log perintah
`/optimize` — Analisis tren + rekomendasi optimasi (AI)

*Setup & Provisioning:*
`/setup` — Panduan setup server (pemula)
`/provision` — Setup LEMP stack dari awal

*Site Management:*
`/site add domain.com` — Tambah site baru
`/site list` — List semua site
`/site ssl domain.com` — Aktifkan SSL
`/site remove domain.com` — Hapus site
`/site wizard` — Wizard interaktif buat site

*Security & Firewall:*
`/security` — Jalankan security audit
`/security_report` — Laporan keamanan cerdas (AI)
`/harden` — Hardening SSH + Fail2Ban
`/harden_ssh_port <port>` — Ubah port SSH (OTP)
`/firewall` — Status firewall
`/fw allow 3306` — Buka port
`/fw deny 3306` — Tutup port

*Backup & Restore:*
`/backup` — Full backup (DB + files)
`/backup db` — Backup databases saja
`/backup list` — List backup tersedia
`/restore <file>` — Restore dari backup (OTP)

*AI & Otomatisasi:*
`/ai [perintah bebas]` — Perintah natural language
   contoh: `/ai restart nginx` atau `/ai cek kenapa disk penuh`
`/cron [jadwal bebas]` — Penjadwalan natural language (AI)
   contoh: `/cron backup db tiap jam 3 pagi`
`/token` — Statistik & biaya token AI
`/model` — Lihat & ganti model AI (haiku/sonnet/opus)

*Lainnya:*
`/confirm <OTP>` — Konfirmasi aksi berisiko
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
        self._plan_running: bool = False  # single-flight guard untuk orchestrator
        self._public_ip_cache: tuple = ("", 0.0)  # (ip, timestamp) — cache 1 jam

    def _generate_otp(self) -> str:
        """Generate a cryptographically secure 4-digit numeric OTP."""
        return str(secrets.randbelow(9000) + 1000)

    def _is_admin(self, update: Update) -> bool:
        return update.effective_user and update.effective_user.id == self.admin_id

    async def _guard(self, update: Update) -> bool:
        """Check if user is authorized admin."""
        if not self._is_admin(update):
            await self._reply(update,
                "⛔ Unauthorized. Hanya admin yang bisa menggunakan bot ini."
            )
            logger.warning(
                f"Unauthorized access attempt from user {update.effective_user.id} "
                f"({update.effective_user.username})"
            )
            return False
        return True

    # ---- Pengiriman pesan aman (#6) ----

    @staticmethod
    async def _reply(update, text, **kwargs):
        """reply_text dengan fallback teks-polos bila Markdown gagal di-parse.

        Konten dinamis (output shell, stderr, pesan AI, domain) bisa berisi
        karakter Markdown tak seimbang sehingga Telegram menolak pesan (400).
        Daripada pesan hilang, kirim ulang tanpa parse_mode.
        """
        send = update.message.reply_text
        try:
            return await send(text, **kwargs)
        except BadRequest as e:
            if "parse" in str(e).lower() and kwargs.get("parse_mode"):
                kwargs.pop("parse_mode", None)
                logger.warning(f"Markdown gagal di-parse, fallback teks polos: {e}")
                return await send(text, **kwargs)
            raise

    @staticmethod
    async def _edit(msg, text, **kwargs):
        """edit_text dengan fallback teks-polos bila Markdown gagal di-parse."""
        edit = msg.edit_text
        try:
            return await edit(text, **kwargs)
        except BadRequest as e:
            if "parse" in str(e).lower() and kwargs.get("parse_mode"):
                kwargs.pop("parse_mode", None)
                logger.warning(f"Markdown gagal di-parse (edit), fallback teks polos: {e}")
                return await edit(text, **kwargs)
            raise

    # ---- Command Handlers ----

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        # Deteksi server baru dan tawarkan onboarding
        setup_hint = ""
        try:
            state = await self.modules["monitor"].get_state_context()
            if "BELUM terpasang" in state:
                setup_hint = "\n\n🆕 Server baru terdeteksi! Ketik `/setup` untuk panduan langkah demi langkah."
        except Exception:
            pass
        await self._reply(update,
            f"🤖 *SyamAdmin Agent*\n\n"
            f"Server: `{self.server_name}`\n"
            f"Status: 🟢 Online\n\n"
            f"Kirim /help untuk daftar perintah.{setup_hint}",
            parse_mode="Markdown",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        await self._reply(update,HELP_TEXT, parse_mode="Markdown")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        msg = await self._reply(update, "⏳ Mengumpulkan status lengkap...")
        report = await self._build_full_status()
        await self._edit(msg, report, parse_mode="Markdown")

    async def _get_public_ip(self) -> str:
        """IP publik dengan cache 1 jam; gagal-aman jadi kosong."""
        ip, ts = self._public_ip_cache
        if ip and (time.time() - ts) < 3600:
            return ip
        r = await self.modules["executor"].run(
            "curl -s --max-time 4 https://api.ipify.org 2>/dev/null || "
            "curl -s --max-time 4 ifconfig.me 2>/dev/null",
            module="status", check=False,
        )
        ip = (r.get("stdout") or "").strip()[:45]
        if ip:
            self._public_ip_cache = (ip, time.time())
        return ip

    async def _build_full_status(self) -> str:
        """Rangkai laporan /status lengkap dari semua modul (paralel, gagal-aman)."""
        ex = self.modules["executor"]
        mon = self.modules["monitor"]
        brain = self.modules["brain"]
        sec = self.modules.get("security")

        async def sh(cmd):
            r = await ex.run(cmd, module="status", check=False)
            return (r.get("stdout") or "").strip()  # abaikan returncode (read-only)

        svc_list = " ".join(MANAGED_SERVICES)
        res = await asyncio.gather(
            mon.collect_metrics(),
            mon.get_state_context(),
            sh("hostname"),
            sh('. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"'),
            sh("uname -r"),
            sh("hostname -I 2>/dev/null | awk '{print $1}'"),
            sh(f"systemctl is-active {svc_list} 2>/dev/null"),
            sh("ufw status 2>/dev/null"),
            sh("ss -tlnH 2>/dev/null"),
            sh("fail2ban-client status sshd 2>/dev/null"),
            self._get_public_ip(),
            return_exceptions=True,
        )
        res = [None if isinstance(r, Exception) else r for r in res]
        (m, state, hostname, os_name, kernel, local_ip,
         svc_out, ufw_out, listen_out, f2b_out, public_ip) = res
        m = m if isinstance(m, dict) else {}
        na = "_n/a_"

        # --- Identitas ---
        ident = [f"🏷 Server : `{self.server_name}`"]
        if hostname:
            ident[0] += f"  (host: `{hostname}`)"
        if os_name:
            ident.append(f"🐧 OS     : {os_name}" + (f"  • kernel {kernel}" if kernel else ""))
        ip_str = local_ip or na
        if public_ip:
            ip_str += f"  (publik: `{public_ip}`)"
        ident.append(f"🌐 IP     : `{ip_str}`" if local_ip else f"🌐 IP     : {ip_str}")
        ident.append(f"⏱ Uptime : `{m.get('uptime_str', na)}`")

        # --- Resource ---
        def bar(v):
            return mon._progress_bar(v) if v is not None else na
        resource = (
            f"*📊 Resource*\n"
            f"CPU {bar(m.get('cpu_percent'))} `{m.get('cpu_percent', '?')}%` "
            f"• {m.get('cpu_count', '?')} core • load `{m.get('load_1', '?')}/{m.get('load_5', '?')}/{m.get('load_15', '?')}`\n"
            f"RAM {bar(m.get('ram_percent'))} `{m.get('ram_percent', '?')}%` "
            f"• `{m.get('ram_used_gb', '?')}/{m.get('ram_total_gb', '?')} GB`\n"
            f"Disk {bar(m.get('disk_percent'))} `{m.get('disk_percent', '?')}%` "
            f"• `{m.get('disk_used_gb', '?')}/{m.get('disk_total_gb', '?')} GB`\n"
            f"Net ↑`{m.get('net_sent_mb', '?')}MB` ↓`{m.get('net_recv_mb', '?')}MB` • proc `{m.get('processes', '?')}`"
        )

        # --- Layanan ---
        states = svc_out.splitlines() if svc_out else []
        parts = []
        for svc, st in zip(MANAGED_SERVICES, states):
            st = st.strip()
            icon = "🟢" if st == "active" else ("⚫" if st in ("inactive", "") else "🔴")
            parts.append(f"{icon} {svc}")
        services = "*🔧 Layanan*\n" + ("  ".join(parts) if parts else na)

        # --- Keamanan & Jaringan ---
        if "Status: active" in ufw_out:
            fw = f"🟢 aktif ({ufw_out.count('ALLOW')} rule)"
        elif "Status: inactive" in ufw_out:
            fw = "🔴 nonaktif"
        else:
            fw = na
        ports = set()
        for line in listen_out.splitlines():
            cols = line.split()
            if len(cols) >= 4:
                p = cols[3].rsplit(":", 1)[-1]
                if p.isdigit():
                    ports.add(int(p))
        ports_sorted = sorted(ports)
        ports_line = ", ".join(str(p) for p in ports_sorted[:14]) + ("…" if len(ports_sorted) > 14 else "")
        ports_line = ports_line or na
        if f2b_out:
            mb = re.search(r"Currently banned:\s*(\d+)", f2b_out)
            f2b = f"🟢 aktif ({mb.group(1) if mb else '0'} IP diblokir)"
        else:
            f2b = na
        ssh_port = getattr(sec, "ssh_port", "?") if sec else "?"
        netsec = (
            f"*🔐 Keamanan & Jaringan*\n"
            f"SSH port : `{ssh_port}`\n"
            f"Firewall : {fw}\n"
            f"Port listen : {ports_line}\n"
            f"Fail2Ban : {f2b}"
        )

        # --- Web stack ---
        webstack = f"*🌐 Web Stack*\n{state or na}"

        # --- AI engine ---
        if not brain.enabled:
            api = "🔴 nonaktif (tanpa API key)"
        elif brain.last_error:
            api = "⚠️ error koneksi"
        else:
            api = "🟢 aktif"
        tok = brain.get_token_statistics()
        ai = (
            f"*🧠 AI Engine*\n"
            f"Model : `{getattr(brain, 'model', '?')}`\n"
            f"API   : {api} • `{tok.get('calls_count', 0)}` panggilan • "
            f"≈ ${tok.get('cost_usd', 0):.4f} (Rp{tok.get('cost_idr', 0):,.0f})"
        )

        # --- Memory Core ---
        mem = brain.get_memory_stats()
        memcore = (
            f"*💾 Memory Core*\n"
            f"Chat: `{mem['chat']}` turn • Pelajaran: `{mem['lessons']}` • Preferensi: `{mem['prefs']}`"
        )

        return (
            "🖥 *SyamAdmin — Status Server*\n"
            + "\n".join(ident)
            + "\n\n" + resource
            + "\n\n" + services
            + "\n\n" + netsec
            + "\n\n" + webstack
            + "\n\n" + ai
            + "\n\n" + memcore
        )

    async def cmd_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        msg = await self._reply(update,"⏳ Checking services...")
        report = await self.modules["monitor"].get_services_status()
        await self._edit(msg,report, parse_mode="Markdown")

    async def cmd_provision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        otp = self._generate_otp()
        await self._reply(update,
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
            await self._reply(update,"❌ Format salah. Gunakan: `/confirm <KODE_OTP>`")
            return

        user_otp = args[0].strip()
        pending = self._pending_confirmations.get(self.admin_id)

        if not pending or pending["expires"] < datetime.now().timestamp():
            await self._reply(update,"❌ Tidak ada aksi yang menunggu konfirmasi atau kode telah kedaluwarsa.")
            return

        if user_otp != pending.get("otp"):
            await self._reply(update,"❌ Kode OTP konfirmasi salah. Silakan coba lagi.")
            return

        # OTP is correct. Proceed to execute.
        del self._pending_confirmations[self.admin_id]
        await self._execute_confirmed_action(update, pending)

    async def cmd_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []

        if not args:
            await self._reply(update,
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
            await self._reply(update,result, parse_mode="Markdown")

        elif action == "list":
            result = await sm.list_sites()
            await self._reply(update,result, parse_mode="Markdown")

        elif action == "ssl" and len(args) >= 2:
            domain = args[1]
            await self._reply(update,f"🔒 Setting up SSL for `{domain}`...", parse_mode="Markdown")
            result = await sm.enable_ssl(domain)
            result = await self._augment_failure("aktivasi SSL", result)
            await self._reply(update,result, parse_mode="Markdown")

        elif action == "remove" and len(args) >= 2:
            domain = args[1]
            otp = self._generate_otp()
            await self._reply(update,
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
            await self._reply(update,"❌ Perintah site tidak valid. Kirim `/site` untuk bantuan.", parse_mode="Markdown")

    async def cmd_security(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        msg = await self._reply(update,"🔍 Running security audit...")
        result = await self.modules["security"].audit()
        await self._edit(msg,result, parse_mode="Markdown")

    async def cmd_harden(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        await self._reply(update,"🔐 Starting hardening process...")
        r1 = await self.modules["security"].harden_ssh()
        r2 = await self.modules["security"].setup_fail2ban()
        r3 = await self.modules["firewall"].setup_defaults()
        r4 = await self.modules["security"].setup_auto_updates()

        summary = f"🔐 *Hardening Complete*\n\n{r1}\n\n{r2}\n\n{r3}\n\n{r4}"
        # Truncate if too long for Telegram
        if len(summary) > 4000:
            summary = summary[:3900] + "\n\n_(truncated)_"
        await self._reply(update,summary, parse_mode="Markdown")

    async def cmd_firewall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        result = await self.modules["firewall"].status()
        await self._reply(update,result, parse_mode="Markdown")

    async def cmd_fw(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Quick firewall commands: /fw allow 3306, /fw deny 8080"""
        if not await self._guard(update):
            return
        args = context.args or []
        fm = self.modules["firewall"]

        if len(args) < 2:
            await self._reply(update,
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
                await self._reply(update,
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

        await self._reply(update,result, parse_mode="Markdown")

    async def cmd_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []
        bm = self.modules["backup"]

        if not args:
            await self._reply(update,"💾 Starting full backup...")
            result = await bm.backup_all()
        elif args[0] == "db":
            result = await bm.backup_db()
        elif args[0] == "files":
            result = await bm.backup_files()
        elif args[0] == "list":
            result = await bm.list_backups()
        else:
            result = "Penggunaan: `/backup` | `/backup db` | `/backup files` | `/backup list`"

        await self._reply(update,result, parse_mode="Markdown")

    async def cmd_restore(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restore dari file backup dengan OTP confirmation."""
        if not await self._guard(update):
            return
        args = context.args or []
        if not args:
            await self._reply(update,
                "Penggunaan: `/restore <nama_file>`\nLihat daftar: `/backup list`",
                parse_mode="Markdown",
            )
            return
        filename = args[0]
        otp = self._generate_otp()
        await self._reply(update,
            f"⚠️ *Konfirmasi Restore* (DESTRUKTIF!)\n\n"
            f"File: `{filename}`\n"
            f"Data saat ini akan ditimpa oleh isi backup.\n\n"
            f"Kirim `/confirm {otp}` atau balas `{otp}` untuk melanjutkan.",
            parse_mode="Markdown",
        )
        self._pending_confirmations[self.admin_id] = {
            "action": "restore",
            "filename": filename,
            "otp": otp,
            "expires": datetime.now().timestamp() + 120,
        }

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

        # Hanya izinkan service yang ada di whitelist untuk mencegah path traversal
        if service not in log_map:
            await self._reply(update,
                f"❌ Service tidak dikenal: `{service}`\n\n"
                f"Service yang tersedia: `nginx`, `mysql`, `auth`, `syslog`, `fail2ban`",
                parse_mode="Markdown",
            )
            return

        log_path = log_map[service]
        r = await self.modules["executor"].run(
            f"tail -30 {log_path} 2>/dev/null || echo 'Log file not found: {log_path}'",
            module="bot",
        )
        await self._reply(update,
            f"📋 *Log: {service}*\n```\n{r['stdout'][:3500]}\n```",
            parse_mode="Markdown",
        )

    async def cmd_audit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        entries = await self.modules["executor"].get_recent_audit(limit=15)
        if not entries:
            await self._reply(update,"📭 Belum ada audit log.")
            return

        lines = ["📋 *Recent Audit Log*\n"]
        for e in entries:
            icon = "✅" if e["status"] == "success" else "❌"
            lines.append(f"{icon} `{e['timestamp']}` [{e['module']}] {e['action'][:60]}")

        await self._reply(update,"\n".join(lines), parse_mode="Markdown")

    async def cmd_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Natural language command processing via AI Brain."""
        if not await self._guard(update):
            return

        user_msg = " ".join(context.args) if context.args else ""
        if not user_msg:
            await self._reply(update,
                "💡 Contoh penggunaan:\n"
                "`/ai restart nginx`\n"
                "`/ai cek kenapa disk penuh`\n"
                "`/ai tambah site example.com dengan laravel`\n"
                "`/ai install redis`",
                parse_mode="Markdown",
            )
            return

        # Single-flight: tolak perintah baru bila ada rencana (plan) sedang berjalan
        if self._plan_running:
            await self._reply(update,
                "⏳ Sebuah rencana (plan) sedang berjalan. Tunggu hingga selesai "
                "sebelum mengirim perintah baru.",
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
            
            msg = await self._reply(update,"🧠 Menganalisis log dan menyiapkan perbaikan...")
            diag = await self.modules["brain"].diagnose_crash(svc, log_content)
            
            otp = self._generate_otp()
            await self._edit(msg,
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

        msg = await self._reply(update,"🧠 Processing...")
        brain = self.modules["brain"]

        # Get current server context for AI (metrics + state)
        metrics = await self.modules["monitor"].collect_metrics()
        state = await self.modules["monitor"].get_state_context()
        context_str = (
            f"CPU: {metrics['cpu_percent']}%, RAM: {metrics['ram_percent']}%, "
            f"Disk: {metrics['disk_percent']}%, Load: {metrics['load_1']}, "
            f"Uptime: {metrics['uptime_str']}\n{state}"
        )

        # Perkaya konteks dengan Memory Core: preferensi admin (Pilar 2) +
        # pelajaran relevan (Pilar 4)
        prefs = brain.get_user_preferences()
        if prefs:
            context_str += "\nPreferensi admin: " + ", ".join(f"{k}={v}" for k, v in prefs.items())
        lessons = brain.query_long_term_memory(user_msg)
        if lessons:
            context_str += "\nPelajaran relevan dari insiden lampau:\n- " + "\n- ".join(lessons)

        # Riwayat percakapan (Pilar 3) untuk konteks multi-turn
        history = brain.get_recent_history(limit=8)

        # Process through AI Brain
        result = await brain.process_command(user_msg, context_str, history=history)

        # Catat turn user (redaksi otomatis di dalam add_to_chat_history)
        brain.add_to_chat_history("user", user_msg)

        if result["action"] == "clarify":
            brain.add_to_chat_history("assistant", result["message"])
            await self._edit(msg,result["message"], parse_mode="Markdown")
            return

        # Jalur PLAN multi-langkah: bila AI menghasilkan steps (>1)
        steps = result.get("steps")
        if steps and len(steps) > 1:
            await self._prepare_plan(update, msg, result, steps)
            return

        # P0 #3: Perintah shell bebas dari AI WAJIB konfirmasi OTP ketat.
        # Keputusan model (confirmation_needed) tidak boleh melewati gerbang ini —
        # safety filter statis saja tidak cukup untuk perintah destruktif yang
        # tak masuk blocklist (mis. `systemctl stop mysql`, `truncate -s 0 ...`).
        forced_otp = (
            result.get("module") == "executor"
            and result.get("action") == "run_command"
        )
        if forced_otp:
            result["confirmation_needed"] = True

        if result.get("confirmation_needed"):
            otp = self._generate_otp()
            # Tampilkan perintah shell yang akan dijalankan agar admin tahu
            # persis apa yang ia setujui sebelum mengetik OTP.
            action_detail = f"`{result['module']}.{result['action']}`"
            cmd_preview = (result.get("params") or {}).get("command")
            if cmd_preview:
                action_detail += f"\nPerintah: `{cmd_preview}`"
            risk_note = (
                "\n\n🔐 *Aksi berisiko* — balasan `ya/ok` tidak berlaku, "
                "wajib kirim kode OTP."
                if forced_otp else ""
            )
            await self._edit(msg,
                f"⚠️ *Konfirmasi Diperlukan*\n\n"
                f"Intent: {result['intent']}\n"
                f"Aksi: {action_detail}\n\n"
                f"{result['message']}{risk_note}\n\n"
                f"Kirim `/confirm {otp}` untuk mengeksekusi (berlaku 60 detik).",
                parse_mode="Markdown",
            )
            brain.add_to_chat_history("assistant", result["message"])
            self._pending_confirmations[self.admin_id] = {
                "action": "ai",
                "result": result,
                "otp": otp,
                "destructive": forced_otp,
                "expires": datetime.now().timestamp() + 60,
            }
            return

        # Execute the parsed action
        response = await self._execute_ai_action(result)
        brain.add_to_chat_history("assistant", response)
        await self._edit(msg, response, parse_mode="Markdown")

        # Tampilkan saran proaktif Jarwo jika ada
        suggestion = result.get("suggestion", "").strip()
        if suggestion:
            await self._reply(update, f"💡 *Jarwo:* _{suggestion}_", parse_mode="Markdown")

    async def _execute_ai_action(self, parsed: dict) -> str:
        """Execute an AI-parsed action through the appropriate module."""
        module_name = parsed.get("module", "")
        action = parsed.get("action", "")
        params = parsed.get("params", {})

        # Resolusi alias: terjemahkan nama-aksi-AI -> method nyata
        action = ACTION_ALIASES.get(module_name, {}).get(action, action)

        try:
            module = self.modules.get(module_name)
            if not module:
                return f"❌ Modul `{module_name}` tidak ditemukan."

            # Route to the correct method
            method = getattr(module, action, None)
            if method and callable(method):
                result = await method(**params) if params else await method()
                return result if isinstance(result, str) else str(result)

            # Special cases (executor)
            if module_name == "executor" and action == "service_restart":
                svc = params.get("service", "")
                r = await self.modules["executor"].service_action(svc, "restart")
                return f"{'✅' if r['success'] else '❌'} Service `{svc}` restart: {r['stdout'] or r['stderr']}"

            if module_name == "executor" and action == "run_command":
                cmd = params.get("command", "")
                r = await self.modules["executor"].run(cmd, module="ai_command")
                return f"```\n{r['stdout'][:3000]}\n```" if r["success"] else f"❌ Error:\n```\n{r['stderr'][:1000]}\n```"

            # Tidak ditemukan: jangan diam-diam — beri tahu user + saran
            logger.warning(f"AI action tak terpetakan: {module_name}.{action}")
            return (
                f"⚠️ Maaf, aksi `{module_name}.{action}` belum tersedia.\n"
                f"Coba `/help` untuk daftar perintah yang didukung."
            )

        except Exception as e:
            logger.error(f"AI action execution error: {e}", exc_info=True)
            return f"❌ Error executing action: {e}"

    # ==================== Multi-step Orchestrator ====================

    @staticmethod
    def _step_is_destructive(step: dict) -> bool:
        """Untuk gating OTP plan: aman (read-only) HANYA bila ada di allowlist.

        Allowlist (bukan blocklist) lebih aman: nama aksi dari model bisa
        bervariasi (mis. `harden_ssh` alih-alih `change_ssh_port`), sehingga
        blocklist mudah meleset. Apa pun yang tidak jelas read-only dianggap
        mengubah state → seluruh plan wajib OTP.
        """
        return step.get("action", "") not in SAFE_READONLY_ACTIONS

    @staticmethod
    def _render_plan_progress(steps: list, statuses: list) -> str:
        icons = {"wait": "💤", "run": "⏳", "done": "✅", "fail": "❌"}
        lines = ["🔄 *Autopilot — Rencana Kerja*\n"]
        for i, step in enumerate(steps):
            label = step.get("message") or f"{step.get('module')}.{step.get('action')}"
            lines.append(f"{icons[statuses[i]]} {i + 1}/{len(steps)} {label}")
        return "\n".join(lines)

    async def _prepare_plan(self, update, msg, result: dict, steps: list):
        """Susun rencana multi-langkah, terapkan gating OTP (reuse #3)."""
        destructive = any(self._step_is_destructive(s) for s in steps)
        otp = self._generate_otp()

        preview = self._render_plan_progress(steps, ["wait"] * len(steps))
        risk_note = (
            "\n\n🔐 *Rencana ini mengandung langkah berisiko* — balasan `ya/ok` "
            "tidak berlaku, wajib kirim kode OTP."
            if destructive else
            "\n\nBalas `ya` atau kirim kode OTP untuk menjalankan."
        )
        text = (
            f"{preview}\n\n_{result.get('message', 'Rencana siap dijalankan.')}_"
            f"{risk_note}\n\nKirim `/confirm {otp}` untuk menjalankan (berlaku 120 detik)."
        )
        self.modules["brain"].add_to_chat_history("assistant", result.get("message", "Rencana disusun."))
        await self._edit(msg, text, parse_mode="Markdown")
        self._pending_confirmations[self.admin_id] = {
            "action": "plan",
            "plan": steps,
            "destructive": destructive,
            "otp": otp,
            "expires": datetime.now().timestamp() + 120,
        }

    async def _execute_multi_step_plan(self, update, plan: list):
        """Eksekusi rencana berurutan: halt-on-failure + live progress + belajar."""
        if self._plan_running:
            await self._reply(update, "⏳ Masih ada rencana berjalan.")
            return
        self._plan_running = True
        statuses = ["wait"] * len(plan)
        progress = await self._reply(
            update, self._render_plan_progress(plan, statuses), parse_mode="Markdown"
        )
        completed = []
        try:
            for i, step in enumerate(plan):
                statuses[i] = "run"
                await self._edit(progress, self._render_plan_progress(plan, statuses), parse_mode="Markdown")

                res = await self._execute_ai_action(step)
                failed = ("❌" in res) or ("gagal" in res.lower())

                if failed:
                    statuses[i] = "fail"
                    label = step.get("message") or f"{step.get('module')}.{step.get('action')}"
                    res = await self._augment_failure(label, res)
                    await self._edit(
                        progress,
                        f"{self._render_plan_progress(plan, statuses)}\n\n"
                        f"⛔ *Dihentikan pada langkah {i + 1}* — sisa langkah dibatalkan.\n\n{res}",
                        parse_mode="Markdown",
                    )
                    self.modules["brain"].add_to_chat_history(
                        "assistant", f"Plan gagal di langkah {i + 1}: {label}"
                    )
                    return

                statuses[i] = "done"
                completed.append(step.get("message") or f"{step.get('module')}.{step.get('action')}")
                await self._edit(progress, self._render_plan_progress(plan, statuses), parse_mode="Markdown")

            # Semua langkah sukses → catat pelajaran (Pilar 4)
            summary = "Plan sukses: " + "; ".join(completed)
            self.modules["brain"].learn_lesson("config_change", summary)
            self.modules["brain"].add_to_chat_history("assistant", summary)
            await self._edit(
                progress,
                f"{self._render_plan_progress(plan, statuses)}\n\n✅ *Seluruh rencana selesai!*",
                parse_mode="Markdown",
            )
        finally:
            self._plan_running = False

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free-text messages (route to AI brain or wizard)."""
        if not await self._guard(update):
            return

        # 1. Check if user is currently inside the interactive wizard (site/setup)
        wizard = self._wizard_states.get(self.admin_id)
        if wizard:
            # Hapus wizard yang sudah kadaluarsa
            if wizard.get("expires", 0) < datetime.now().timestamp():
                del self._wizard_states[self.admin_id]
                await self._reply(update,
                    "⏰ Sesi wizard telah berakhir (timeout 10 menit). "
                    "Mulai ulang dengan `/site wizard` atau `/setup`.",
                    parse_mode="Markdown",
                )
                return
            user_text = update.message.text.strip()
            state = wizard["state"]

            # Fase 7: Handler state SETUP_MENU (onboarding wizard)
            if state == "SETUP_MENU":
                choice = user_text.strip()
                if choice == "1":
                    del self._wizard_states[self.admin_id]
                    await self.cmd_provision(update, context)
                    return
                elif choice == "2":
                    del self._wizard_states[self.admin_id]
                    otp = self._generate_otp()
                    self._pending_confirmations[self.admin_id] = {
                        "action": "harden_all", "otp": otp,
                        "expires": datetime.now().timestamp() + 120,
                    }
                    await self._reply(update,
                        f"🔐 Akan menjalankan hardening SSH + Fail2Ban + Firewall + Auto-update.\n"
                        f"Kirim `/confirm {otp}` atau balas `{otp}`.",
                        parse_mode="Markdown",
                    )
                    return
                elif choice == "3":
                    self._wizard_states[self.admin_id] = {
                        "state": "DOMAIN",
                        "expires": datetime.now().timestamp() + 600,
                    }
                    await self._reply(update,
                        "👉 Masukkan nama domain (mis. `contoh.com`):",
                        parse_mode="Markdown",
                    )
                    return
                elif choice in ("selesai", "done"):
                    del self._wizard_states[self.admin_id]
                    await self._reply(update,"✅ Panduan ditutup. Ketik `/help` kapan saja.")
                    return
                else:
                    await self._reply(update,
                        "❌ Pilihan tidak valid. Ketik `1`, `2`, `3`, atau `selesai`."
                    )
                    return

            elif state == "DOMAIN":
                domain_regex = r"^[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+$"
                if not re.match(domain_regex, user_text):
                    await self._reply(update,
                        "❌ Format domain tidak valid. Silakan masukkan domain yang benar (misal: `situsku.com`):"
                    )
                    return
                
                wizard["domain"] = user_text.lower()
                wizard["state"] = "TYPE"
                await self._reply(update,
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
                    await self._reply(update,
                        "❌ Jenis framework tidak dikenal. Silakan ketik salah satu dari: `default`, `wordpress`, atau `laravel`:"
                    )
                    return
                
                wizard["framework"] = framework
                wizard["state"] = "DB"
                await self._reply(update,
                    f"🚀 *Framework terpilih:* `{framework}`\n\n"
                    f"👉 *Langkah 3:* Apakah Anda membutuhkan database MySQL untuk situs ini?\n"
                    f"Ketik *ya* atau *tidak*:"
                )
                return

            elif state == "DB":
                choice = user_text.lower()
                if choice not in ("ya", "tidak"):
                    await self._reply(update,
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
                
                await self._reply(update,
                    f"📝 *Ringkasan Konfigurasi Website*\n\n"
                    f"• *Domain*: `{domain}`\n"
                    f"• *Framework/Platform*: `{framework}`\n"
                    f"• *Buat Database MySQL*: `{'Ya' if need_db else 'Tidak'}`\n\n"
                    f"⚠️ *Peringatan*: Proses ini akan mengubah konfigurasi Nginx dan Firewall.\n"
                    f"Kirim `/confirm {otp}` atau cukup balas dengan `{otp}` untuk mengeksekusi.",
                    parse_mode="Markdown"
                )
                return

        # 2. Check for pending OTP confirmation (+ terima ya/ok untuk non-destruktif)
        pending = self._pending_confirmations.get(self.admin_id)
        if pending and pending["expires"] > datetime.now().timestamp():
            user_text = update.message.text.strip().lower()
            is_otp = user_text == pending.get("otp")
            is_affirmative = (
                user_text in AFFIRMATIVE_WORDS
                and pending["action"] not in DESTRUCTIVE_ACTIONS
                and not pending.get("destructive")
            )
            if is_otp or is_affirmative:
                del self._pending_confirmations[self.admin_id]
                await self._execute_confirmed_action(update, pending)
                return
            # Jika aksi destruktif & user balas "ya": ingatkan butuh OTP
            if user_text in AFFIRMATIVE_WORDS:
                await self._reply(update,
                    "🔐 Aksi ini berisiko. Mohon kirim *kode OTP* yang tertera untuk konfirmasi.",
                    parse_mode="Markdown",
                )
                return

        # 3. Otherwise, treat as AI command
        context.args = update.message.text.split()
        await self.cmd_ai(update, context)

    async def cmd_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display real-time Claude API token utilization statistics and costs."""
        if not await self._guard(update):
            return
        
        msg = await self._reply(update,"⏳ Mengambil data penggunaan token...")
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
            f"_Note: Estimasi dihitung berdasarkan tarif model `{getattr(self.modules['brain'], 'model', '?')}`._"
        )
        await self._edit(msg,report, parse_mode="Markdown")

    async def cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan atau ganti model AI yang digunakan SyamAdmin."""
        if not await self._guard(update):
            return

        brain = self.modules.get("brain")
        current = getattr(brain, "model", "?")

        # Tanpa argumen → tampilkan daftar
        if not context.args:
            lines = ["🧠 *Model AI SyamAdmin*\n"]
            lines.append(f"Model aktif: `{current}`\n")
            lines.append("*Model tersedia (terkini):*\n")
            for model_id, info in AVAILABLE_MODELS.items():
                marker = "✅" if model_id == current else "○"
                idr_in = int(info["input_usd_per_mtok"] * 16300)
                idr_out = int(info["output_usd_per_mtok"] * 16300)
                lines.append(
                    f"{marker} `{model_id}`\n"
                    f"   {info['name']} — {info['speed']}\n"
                    f"   Input: ${info['input_usd_per_mtok']}/MTok (≈Rp{idr_in:,}/MTok)\n"
                    f"   Output: ${info['output_usd_per_mtok']}/MTok (≈Rp{idr_out:,}/MTok)\n"
                    f"   _{info['note']}_\n"
                )
            lines.append("Ganti model: `/model haiku` · `/model sonnet` · `/model opus`")
            lines.append("atau gunakan ID penuh: `/model claude-sonnet-4-6`")
            await self._reply(update, "\n".join(lines), parse_mode="Markdown")
            return

        # Resolusi shorthand → full model ID
        shorthand = {
            "haiku": "claude-haiku-4-5-20251001",
            "sonnet": "claude-sonnet-4-6",
            "opus": "claude-opus-4-8",
        }
        target = context.args[0].lower()
        model_id = shorthand.get(target, target)

        if model_id not in AVAILABLE_MODELS:
            ids = "\n".join(f"• `{k}`" for k in AVAILABLE_MODELS)
            await self._reply(
                update,
                f"❌ Model tidak dikenal: `{target}`\n\nPilihan valid:\n{ids}\n\n"
                f"Atau gunakan shorthand: `haiku` · `sonnet` · `opus`",
                parse_mode="Markdown",
            )
            return

        if model_id == current:
            await self._reply(update, f"ℹ️ Model sudah aktif: `{model_id}`", parse_mode="Markdown")
            return

        if brain and brain.set_model(model_id):
            info = AVAILABLE_MODELS[model_id]
            idr_in = int(info["input_usd_per_mtok"] * 16300)
            idr_out = int(info["output_usd_per_mtok"] * 16300)
            await self._reply(
                update,
                f"✅ *Model berhasil diganti*\n\n"
                f"• Model baru: `{model_id}`\n"
                f"• Nama: {info['name']}\n"
                f"• Kecepatan: {info['speed']}\n"
                f"• Input: ${info['input_usd_per_mtok']}/MTok (≈Rp{idr_in:,})\n"
                f"• Output: ${info['output_usd_per_mtok']}/MTok (≈Rp{idr_out:,})\n\n"
                f"_{info['note']}_\n\n"
                f"Perubahan langsung aktif dan disimpan ke config.env.",
                parse_mode="Markdown",
            )
        else:
            await self._reply(update, "❌ Gagal mengganti model.", parse_mode="Markdown")

    async def cmd_cron(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Natural language scheduling via AI."""
        if not await self._guard(update):
            return
            
        user_msg = " ".join(context.args) if context.args else ""
        if not user_msg:
            await self._reply(update,
                "💡 Contoh penggunaan:\n"
                "`/cron backup db setiap jam 3 pagi`\n"
                "`/cron audit keamanan setiap hari minggu jam 11 malam`\n"
                "`/cron scan rootkit tiap jam 12 malam`",
                parse_mode="Markdown"
            )
            return
            
        msg = await self._reply(update,"🧠 Menganalisis waktu penjadwalannya...")
        res = await self.modules["brain"].parse_cron_instruction(user_msg)
        
        if not res.get("success"):
            await self._edit(msg,res.get("message", "❌ Gagal memahami waktu penjadwalan."), parse_mode="Markdown")
            return
            
        otp = self._generate_otp()
        await self._edit(msg,
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
            
        msg = await self._reply(update,"📊 Membaca tren historis dan menyusun rekomendasi...")
        
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
            
        await self._edit(msg,report_text, parse_mode="Markdown")

    async def cmd_site_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Initiate the step-by-step interactive site setup wizard."""
        if not await self._guard(update):
            return

        _WIZARD_TIMEOUT = 600  # 10 menit
        self._wizard_states[self.admin_id] = {
            "state": "DOMAIN",
            "expires": datetime.now().timestamp() + _WIZARD_TIMEOUT,
        }
        await self._reply(update,
            "🧙‍♂️ *Interactive Site Provisioning Wizard*\n\n"
            "Mari siapkan website baru Anda langkah demi langkah.\n\n"
            "👉 *Langkah 1:* Silakan masukkan *nama domain* untuk website Anda (misal: `example.com`):",
            parse_mode="Markdown",
        )

    async def cmd_security_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display an AI security log scanner intelligence report."""
        if not await self._guard(update):
            return
        msg = await self._reply(update,"⏳ Menganalisis log keamanan server...")
        report = await self.modules["security"].scan_auth_logs(brain=self.modules["brain"])
        await self._edit(msg,report, parse_mode="Markdown")

    async def cmd_harden_ssh_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Request shifting the SSH port to a non-standard port with dynamic OTP verification."""
        if not await self._guard(update):
            return
        args = context.args or []
        if not args:
            await self._reply(update,"❌ Format salah. Gunakan: `/harden_ssh_port <PORT_BARU>` (rentang 1024 - 65535)")
            return
        try:
            new_port = int(args[0])
        except ValueError:
            await self._reply(update,"❌ Port harus berupa angka numerik valid.")
            return
            
        otp = self._generate_otp()
        await self._reply(update,
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

    async def cmd_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Panduan onboarding server untuk pemula."""
        if not await self._guard(update):
            return
        self._wizard_states[self.admin_id] = {
            "state": "SETUP_MENU",
            "expires": datetime.now().timestamp() + 600,
        }
        await self._reply(update,
            "🧭 *Panduan Setup Server (Pemula)*\n\n"
            "Saya akan bantu langkah demi langkah:\n"
            "1️⃣ Pasang LEMP (web server)\n"
            "2️⃣ Amankan server (hardening + firewall)\n"
            "3️⃣ Buat website pertama\n\n"
            "Ketik nomor langkah (`1`/`2`/`3`) atau `selesai`.",
            parse_mode="Markdown",
        )

    async def _augment_failure(self, operation: str, text: str) -> str:
        """Jika text indikasi kegagalan, tambahkan penjelasan AI ramah-pemula."""
        if "❌" not in text and "gagal" not in text.lower():
            return text
        brain = self.modules.get("brain")
        if not (brain and brain.enabled):
            return text
        explanation = await brain.explain_error(operation, text)
        if explanation:
            return f"{text}\n\n🧠 *Penjelasan:*\n{explanation}"
        return text

    async def _execute_confirmed_action(self, update: Update, pending: dict):
        """Common executor for all confirmed actions via OTP validation."""
        action = pending["action"]
        
        if action == "provision":
            await self._reply(update,"🚀 Memulai provisioning... (ini memakan waktu 5-10 menit)")
            asyncio.create_task(self.modules["provisioner"].install_lemp())

        elif action == "remove_site":
            domain = pending["domain"]
            await self._reply(update,f"🗑️ Menghapus site `{domain}`...")
            result = await self.modules["site_manager"].remove_site(domain)
            await self._reply(update,result, parse_mode="Markdown")

        elif action == "deny_ssh":
            port = pending["port"]
            await self._reply(update,f"🛑 Menutup port SSH `{port}`...")
            result = await self.modules["firewall"].deny_port(port)
            await self._reply(update,result, parse_mode="Markdown")

        elif action == "ai":
            await self._reply(update,"⚙️ Mengeksekusi aksi AI yang dikonfirmasi...")
            response = await self._execute_ai_action(pending["result"])
            await self._reply(update, response, parse_mode="Markdown")
            suggestion = pending.get("result", {}).get("suggestion", "").strip()
            if suggestion:
                await self._reply(update, f"💡 *Jarwo:* _{suggestion}_", parse_mode="Markdown")

        elif action == "plan":
            await self._execute_multi_step_plan(update, pending["plan"])

        elif action == "repair_service":
            cmd = pending["command"]
            svc = pending["service"]
            await self._reply(update,f"🔧 Menjalankan perbaikan otomatis untuk `{svc}`...")
            result = await self.modules["executor"].run(cmd, module="auto_repair")
            if result["success"]:
                status = await self.modules["executor"].run(f"systemctl is-active {svc}", module="auto_repair", check=False)
                active_str = "🟢 Aktif" if status["stdout"].strip() == "active" else "🔴 Masih Gagal"
                await self._reply(update,
                    f"✅ *Perbaikan Selesai!*\n\n"
                    f"Output:\n```\n{result['stdout'][:2000]}\n```\n"
                    f"Status Layanan: *{active_str}*",
                    parse_mode="Markdown"
                )
            else:
                await self._reply(update,
                    f"❌ *Perbaikan Gagal!*\n\n"
                    f"Error:\n```\n{result['stderr'][:2000]}\n```",
                    parse_mode="Markdown"
                )

        elif action == "optimize_system":
            cmd = pending["command"]
            svc = pending["service"]
            await self._reply(update,f"⚙️ Menerapkan optimasi sistem untuk `{svc}`...", parse_mode="Markdown")
            result = await self.modules["executor"].run(cmd, module="optimization")
            if result["success"]:
                await self._reply(update,
                    f"✅ *Optimasi Berhasil Diterapkan!*\n\n"
                    f"Output:\n```\n{result['stdout'][:2000]}\n```",
                    parse_mode="Markdown"
                )
            else:
                await self._reply(update,
                    f"❌ *Gagal menerapkan optimasi!*\n\n"
                    f"Error:\n```\n{result['stderr'][:2000]}\n```",
                    parse_mode="Markdown"
                )

        elif action == "add_cron":
            cron_expr = pending["cron_expression"]
            cmd = pending["command"]
            summary = pending["readable_summary"]
            await self._reply(update,f"⏳ Menjadwalkan `{cmd}`...")
            result = await self.modules["executor"].add_cron_job(cron_expr, cmd)
            if result["success"]:
                await self._reply(update,
                    f"✅ *Penjadwalan Berhasil!* 📅\n\n"
                    f"• *Tugas*: `{cmd}`\n"
                    f"• *Jadwal*: {summary}\n"
                    f"• *Cron Expression*: `{cron_expr}`",
                    parse_mode="Markdown"
                )
            else:
                await self._reply(update,
                    f"❌ *Gagal menjadwalkan tugas!*\n\n"
                    f"Error:\n```\n{result['stderr']}\n```",
                    parse_mode="Markdown"
                )

        elif action == "wizard_provision":
            domain = pending["domain"]
            framework = pending["framework"]
            db = pending["db"]
            
            await self._reply(update,f"⏳ *Memulai instalasi website `{domain}`...*", parse_mode="Markdown")
            
            sm = self.modules["site_manager"]
            site_result = await sm.add_site(domain, framework=framework)
            
            db_info = ""
            if db:
                clean_domain = re.sub(r"[^a-zA-Z0-9]", "", domain.split(".")[0])[:12]
                db_name = f"db_{clean_domain}_{secrets.token_hex(2)}"
                db_user = f"usr_{clean_domain}"
                db_pass = secrets.token_urlsafe(10)
                
                await self._reply(update,f"🗄️ *Membuat database `{db_name}`...*", parse_mode="Markdown")
                
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
            
            await self._reply(update,f"🔒 *Menyiapkan SSL Let's Encrypt untuk `{domain}`...*", parse_mode="Markdown")
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
                
            await self._reply(update,final_report, parse_mode="Markdown")

        elif action == "restore":
            filename = pending["filename"]
            await self._reply(update,f"♻️ Memulihkan dari `{filename}`...", parse_mode="Markdown")
            result = await self.modules["backup"].restore(filename)
            result = await self._augment_failure("restore backup", result)
            await self._reply(update,result, parse_mode="Markdown")

        elif action == "harden_all":
            await self._reply(update,"🔐 Menjalankan hardening menyeluruh...")
            r1 = await self.modules["security"].harden_ssh()
            r2 = await self.modules["security"].setup_fail2ban()
            r3 = await self.modules["firewall"].setup_defaults()
            r4 = await self.modules["security"].setup_auto_updates()
            summary = f"🔐 *Hardening Selesai*\n\n{r1}\n\n{r2}\n\n{r3}\n\n{r4}"
            await self._reply(update,summary[:4000], parse_mode="Markdown")

        elif action == "change_ssh_port":
            new_port = pending["new_port"]
            await self._reply(update,f"🔐 *Mengubah port SSH ke `{new_port}`...*", parse_mode="Markdown")
            result = await self.modules["security"].change_ssh_port(new_port)
            await self._reply(update,result, parse_mode="Markdown")

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
        app.add_handler(CommandHandler("model", self.cmd_model))
        app.add_handler(CommandHandler("cron", self.cmd_cron))
        app.add_handler(CommandHandler("optimize", self.cmd_optimize))
        app.add_handler(CommandHandler("security_report", self.cmd_security_report))
        app.add_handler(CommandHandler("harden_ssh_port", self.cmd_harden_ssh_port))
        app.add_handler(CommandHandler("restore", self.cmd_restore))
        app.add_handler(CommandHandler("setup", self.cmd_setup))

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
            BotCommand("model", "Lihat & ganti model AI"),
            BotCommand("cron", "AI Task Scheduler"),
            BotCommand("optimize", "AI Resource Optimizer"),
            BotCommand("restore", "Restore dari backup"),
            BotCommand("setup", "Panduan setup pemula"),
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
