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
from modules.brain import AVAILABLE_MODELS, PROFILE_FIELDS

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
    "service_stop", "apt_upgrade", "reboot", "app_update",
}

# Aksi read-only (allowlist) — dipakai gating OTP orchestrator. Step plan yang
# TIDAK ada di sini dianggap mengubah state → seluruh plan wajib OTP.
SAFE_READONLY_ACTIONS = {
    "status", "services", "top_processes", "disk_usage", "connections",
    "list_rules", "list_sites", "list_backups", "audit", "check_updates",
    "scan_rootkit", "get_status_report", "get_services_status",
    "get_disk_report", "get_top_processes", "get_connections",
}

# ──────────────────────────────────────────────────────────────────────────
# COMMAND REGISTRY — SUMBER KEBENARAN TUNGGAL
#
# Satu registry mendrive tiga hal sekaligus agar tidak pernah drift:
#   1) registrasi CommandHandler   2) menu Telegram (set_my_commands)
#   3) HELP_TEXT
# Field per-entri: (command, handler_method, usage, help_desc, menu_desc)
#   usage     : contoh argumen untuk HELP (boleh "")
#   menu_desc : None → tidak dimunculkan di menu Telegram
# ──────────────────────────────────────────────────────────────────────────
COMMAND_REGISTRY = [
    ("🖥 Server & Monitoring", [
        ("status",   "cmd_status",   "",                                  "Status server lengkap (CPU, RAM, Disk, layanan)", "Status server"),
        ("services", "cmd_services", "",                                  "Status semua layanan terkelola",                  "Status layanan"),
        ("service",  "cmd_service",  "restart|stop|start|status <nama>",  "Kontrol layanan langsung (tanpa AI)",             "Kontrol layanan"),
        ("logs",     "cmd_logs",     "[layanan] [baris]",                 "Lihat log (nginx, nginx-access, mysql, auth, syslog, fail2ban, syamadmin)", "Lihat log"),
        ("audit",    "cmd_audit",    "",                                  "Riwayat perintah (audit log)",                    "Audit log"),
        ("optimize", "cmd_optimize", "",                                  "Analisis tren + rekomendasi optimasi (AI)",       "Optimasi (AI)"),
    ]),
    ("🚀 Setup & Provisioning", [
        ("setup",     "cmd_setup",     "", "Panduan setup server langkah demi langkah (pemula)", "Panduan setup pemula"),
        ("provision", "cmd_provision", "", "Pasang LEMP stack dari awal (OTP)",                  "Pasang LEMP stack"),
    ]),
    ("🌐 Manajemen Site", [
        ("site", "cmd_site", "add|list|ssl|remove|wizard …", "Kelola situs Nginx + SSL (ketik `/site` untuk detail)", "Kelola situs"),
    ]),
    ("🔐 Keamanan & Firewall", [
        ("security", "cmd_security", "audit|report|harden|ssh-port <port>", "Audit, laporan AI, hardening, ubah port SSH", "Keamanan"),
        ("fw",       "cmd_fw",       "status|allow|deny|rules <port>",      "Kelola firewall UFW",                         "Firewall UFW"),
    ]),
    ("💾 Backup & Restore", [
        ("backup",  "cmd_backup",  "[db|files|list]", "Backup penuh / DB / file, atau daftar backup", "Backup"),
        ("restore", "cmd_restore", "<file>",          "Pulihkan dari backup (OTP)",                    "Restore backup"),
    ]),
    ("🤖 AI & Otomatisasi", [
        ("ai",    "cmd_ai",    "[perintah bebas]",    "Perintah natural language (mis. `/ai restart nginx`)", "Perintah AI"),
        ("cron",  "cmd_cron",  "[jadwal bebas]",      "Penjadwalan natural language (mis. `/cron backup db jam 3 pagi`)", "Penjadwal AI"),
        ("token", "cmd_token", "",                    "Statistik & biaya token AI",                          "Statistik token AI"),
        ("model", "cmd_model", "[haiku|sonnet|opus]", "Lihat & ganti model AI",                              "Model AI"),
    ]),
    ("👤 Profil & Konteks", [
        ("profile", "cmd_profile", "setup|set <field> <nilai>|reset",
         "Profil admin & konteks server agar Jarwo lebih personal", "Profil admin"),
    ]),
    ("🛡️ PeFi — Pre-Emptive Firewall", [
        ("pefi", "cmd_pefi", "threats|rules|report|health|scan|block|unblock|whitelist|ignore|autoblock",
         "Firewall pre-emptive berbasis AI (ketik `/pefi` untuk detail)", "PeFi firewall AI"),
    ]),
    ("⚙️ Sistem", [
        ("update",    "cmd_update",    "[check|now]", "Cek & pasang update SyamAdmin terbaru dari GitHub (OTP)", "Update SyamAdmin"),
        ("sysupdate", "cmd_sysupdate", "",            "Update & upgrade paket OS via apt (OTP)",                 "Update paket OS"),
        ("reboot",    "cmd_reboot",    "",            "Reboot server (OTP)",                                     "Reboot server"),
        ("confirm",   "cmd_confirm",   "<OTP>",       "Konfirmasi aksi berisiko",                                None),
        ("help",      "cmd_help",      "",            "Tampilkan bantuan ini",                                   "Bantuan"),
    ]),
]

# Alias (tidak di menu) — kompatibilitas mundur untuk command yang kini digabung,
# plus entry-point /start.
COMMAND_ALIASES = [
    ("start",            "cmd_start"),
    ("firewall",         "cmd_firewall"),          # → /fw status
    ("harden",           "cmd_harden"),            # → /security harden
    ("security_report",  "cmd_security_report"),   # → /security report
    ("harden_ssh_port",  "cmd_harden_ssh_port"),   # → /security ssh-port
    ("svc",              "cmd_service"),           # → /service
]


def _build_help_text() -> str:
    """Bangun HELP_TEXT dari COMMAND_REGISTRY (sumber kebenaran tunggal)."""
    lines = ["🤖 *SyamAdmin — AI Sysadmin Agent*\n"]
    for title, entries in COMMAND_REGISTRY:
        lines.append(f"*{title}:*")
        for cmd, _handler, usage, desc, _menu in entries:
            sig = f"/{cmd}" + (f" {usage}" if usage else "")
            lines.append(f"`{sig}` — {desc}")
        lines.append("")
    lines.append("_Tip: ketik command tanpa argumen (mis. `/site`, `/fw`, `/security`, `/pefi`) untuk sub-bantuan._")
    return "\n".join(lines)


def _build_menu_commands():
    """Bangun daftar BotCommand untuk set_my_commands dari registry."""
    cmds = []
    for _title, entries in COMMAND_REGISTRY:
        for cmd, _handler, _usage, _desc, menu in entries:
            if menu:
                cmds.append(BotCommand(cmd, menu))
    return cmds


HELP_TEXT = _build_help_text()


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

    @staticmethod
    def _otp_line(otp: str, seconds: int = 60) -> str:
        """Kalimat konfirmasi OTP yang SERAGAM untuk seluruh flow.

        Baik balas-angka langsung maupun `/confirm <otp>` sama-sama valid —
        satu frasa konsisten menghindari kebingungan antar-command.
        """
        return f"Balas `{otp}` atau kirim `/confirm {otp}` untuk melanjutkan (berlaku {seconds} detik)."

    def _arm_confirmation(self, action: str, otp: str, seconds: int = 60, **extra) -> None:
        """Set pending confirmation secara konsisten (expiry seragam per-pemanggil)."""
        self._pending_confirmations[self.admin_id] = {
            "action": action,
            "otp": otp,
            "expires": datetime.now().timestamp() + seconds,
            **extra,
        }

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

        # Tawarkan pengisian profil bila admin belum kenalan
        profile_hint = ""
        brain = self.modules.get("brain")
        greeting = "Halo"
        try:
            if brain and brain.is_profile_empty():
                profile_hint = (
                    "\n\n👋 Kita belum kenalan! Ketik `/profile setup` biar Jarwo bisa "
                    "menyapa dengan namamu & paham konteks kerjamu."
                )
            elif brain:
                greeting = f"Halo *{brain.get_admin_nickname()}*"
        except Exception:
            pass

        await self._reply(update,
            f"🤖 *SyamAdmin Agent*\n\n"
            f"{greeting}! Server: `{self.server_name}`\n"
            f"Status: 🟢 Online\n\n"
            f"Kirim /help untuk daftar perintah.{setup_hint}{profile_hint}",
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
        updater = self.modules.get("updater")
        ver = updater.get_local_version() if updater else ""
        ident = [f"🏷 Server : `{self.server_name}`" + (f"  • v`{ver}`" if ver else "")]
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
        msg = await self._reply(update,"⏳ Mengecek status layanan...")
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
            f"{self._otp_line(otp)}",
            parse_mode="Markdown",
        )
        self._arm_confirmation("provision", otp, 60)

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
            msg = await self._reply(update,f"🔒 Menyiapkan SSL untuk `{domain}`...", parse_mode="Markdown")
            result = await sm.enable_ssl(domain)
            result = await self._augment_failure("aktivasi SSL", result)
            await self._edit(msg,result, parse_mode="Markdown")

        elif action == "remove" and len(args) >= 2:
            domain = args[1]
            otp = self._generate_otp()
            await self._reply(update,
                f"🗑️ *Konfirmasi Hapus Site `{domain}`*\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("remove_site", otp, 60, domain=domain)

        else:
            await self._reply(update,"❌ Perintah site tidak valid. Kirim `/site` untuk bantuan.", parse_mode="Markdown")

    async def cmd_security(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Router keamanan: /security audit|report|harden|ssh-port <port>."""
        if not await self._guard(update):
            return
        args = context.args or []
        sub = args[0].lower() if args else "audit"

        if sub == "audit":
            await self._do_security_audit(update)
        elif sub == "report":
            await self._do_security_report(update)
        elif sub == "harden":
            await self._do_harden(update)
        elif sub in ("ssh-port", "ssh_port", "sshport"):
            await self._do_ssh_port(update, args[1:])
        else:
            await self._reply(update,
                "🔐 *Penggunaan /security:*\n"
                "`/security audit` — jalankan security audit\n"
                "`/security report` — laporan keamanan cerdas (AI)\n"
                "`/security harden` — hardening SSH + Fail2Ban + firewall + auto-update\n"
                "`/security ssh-port <port>` — ubah port SSH (OTP)",
                parse_mode="Markdown",
            )

    async def _do_security_audit(self, update: Update):
        msg = await self._reply(update,"🔍 Menjalankan security audit...")
        result = await self.modules["security"].audit()
        await self._edit(msg,result, parse_mode="Markdown")

    async def _do_harden(self, update: Update):
        """Hardening menyeluruh dengan indikator progres bertahap."""
        msg = await self._reply(update,"🔐 *Memulai hardening...*\n⏳ 1/4 SSH hardening", parse_mode="Markdown")
        r1 = await self.modules["security"].harden_ssh()
        await self._edit(msg,"🔐 *Hardening...*\n✅ 1/4 SSH\n⏳ 2/4 Fail2Ban", parse_mode="Markdown")
        r2 = await self.modules["security"].setup_fail2ban()
        await self._edit(msg,"🔐 *Hardening...*\n✅ 1/4 SSH\n✅ 2/4 Fail2Ban\n⏳ 3/4 Firewall", parse_mode="Markdown")
        r3 = await self.modules["firewall"].setup_defaults()
        await self._edit(msg,"🔐 *Hardening...*\n✅ 1/4 SSH\n✅ 2/4 Fail2Ban\n✅ 3/4 Firewall\n⏳ 4/4 Auto-update", parse_mode="Markdown")
        r4 = await self.modules["security"].setup_auto_updates()

        summary = f"🔐 *Hardening Selesai*\n\n{r1}\n\n{r2}\n\n{r3}\n\n{r4}"
        if len(summary) > 4000:
            summary = summary[:3900] + "\n\n_(dipotong)_"
        await self._edit(msg,summary, parse_mode="Markdown")

    async def cmd_harden(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Alias: /security harden (kompatibilitas mundur)."""
        if not await self._guard(update):
            return
        await self._do_harden(update)

    async def cmd_firewall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Alias: /fw status (kompatibilitas mundur)."""
        if not await self._guard(update):
            return
        msg = await self._reply(update,"🧱 Mengambil status firewall...")
        result = await self.modules["firewall"].status()
        await self._edit(msg,result, parse_mode="Markdown")

    async def cmd_fw(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Firewall UFW: /fw status|allow|deny|rules <port>."""
        if not await self._guard(update):
            return
        args = context.args or []
        fm = self.modules["firewall"]
        action = args[0].lower() if args else "status"

        # status & rules: tidak butuh argumen port
        if action == "status":
            msg = await self._reply(update,"🧱 Mengambil status firewall...")
            result = await fm.status()
            await self._edit(msg,result, parse_mode="Markdown")
            return
        if action == "rules":
            msg = await self._reply(update,"🧱 Memuat daftar rule...")
            result = await fm.list_rules()
            await self._edit(msg,result, parse_mode="Markdown")
            return

        if action not in ("allow", "deny") or len(args) < 2:
            await self._reply(update,
                "🧱 *Penggunaan /fw:*\n"
                "`/fw status` — status firewall\n"
                "`/fw rules` — daftar rule\n"
                "`/fw allow 3306` — buka port\n"
                "`/fw deny 8080` — tutup port",
                parse_mode="Markdown",
            )
            return

        port = args[1]
        if action == "allow":
            msg = await self._reply(update,f"🧱 Membuka port `{port}`...", parse_mode="Markdown")
            result = await fm.allow_port(port)
            await self._edit(msg,result, parse_mode="Markdown")
            return

        # action == "deny"
        ssh_port = os.environ.get("SSH_PORT", "22")
        if port == ssh_port or port == "22":
            otp = self._generate_otp()
            await self._reply(update,
                f"⚠️ *Peringatan Keamanan Port SSH ({port})*\n\n"
                "Anda akan menutup akses port SSH! Tindakan ini dapat mengunci akses Anda ke server.\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("deny_ssh", otp, 60, port=port)
            return
        msg = await self._reply(update,f"🧱 Menutup port `{port}`...", parse_mode="Markdown")
        result = await fm.deny_port(port)
        await self._edit(msg,result, parse_mode="Markdown")

    async def cmd_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []
        bm = self.modules["backup"]

        if args and args[0] not in ("db", "files", "list"):
            await self._reply(update,
                "💾 *Penggunaan /backup:*\n"
                "`/backup` — backup penuh (DB + file)\n"
                "`/backup db` — backup database saja\n"
                "`/backup files` — backup file situs saja\n"
                "`/backup list` — daftar backup tersedia",
                parse_mode="Markdown",
            )
            return

        if not args:
            msg = await self._reply(update,"💾 Memulai backup penuh...")
            result = await bm.backup_all()
        elif args[0] == "db":
            msg = await self._reply(update,"💾 Backup database...")
            result = await bm.backup_db()
        elif args[0] == "files":
            msg = await self._reply(update,"💾 Backup file situs...")
            result = await bm.backup_files()
        else:  # list
            msg = await self._reply(update,"💾 Memuat daftar backup...")
            result = await bm.list_backups()

        await self._edit(msg,result, parse_mode="Markdown")

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
            f"{self._otp_line(otp, 120)}",
            parse_mode="Markdown",
        )
        self._arm_confirmation("restore", otp, 120, filename=filename)

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = context.args or []
        service = args[0].lower() if args else "syslog"

        # Jumlah baris opsional (arg ke-2), clamp 1..200
        lines_n = 30
        if len(args) > 1 and args[1].isdigit():
            lines_n = max(1, min(200, int(args[1])))

        log_map = {
            "nginx": "/var/log/nginx/error.log",
            "nginx-access": "/var/log/nginx/access.log",
            "mysql": "/var/log/mysql/error.log",
            "auth": "/var/log/auth.log",
            "syslog": "/var/log/syslog",
            "fail2ban": "/var/log/fail2ban.log",
        }

        # 'syamadmin' = log agen sendiri via journalctl (fallback ke LOG_FILE)
        if service == "syamadmin":
            log_file = os.environ.get("LOG_FILE", "/var/log/syamadmin/agent.log")
            cmd = (
                f"journalctl -u syamadmin -n {lines_n} --no-pager 2>/dev/null "
                f"|| tail -n {lines_n} {log_file} 2>/dev/null "
                f"|| echo 'Log SyamAdmin tidak ditemukan.'"
            )
        elif service in log_map:
            log_path = log_map[service]
            cmd = f"tail -n {lines_n} {log_path} 2>/dev/null || echo 'Log file tidak ditemukan: {log_path}'"
        else:
            await self._reply(update,
                f"❌ Layanan log tidak dikenal: `{service}`\n\n"
                f"Tersedia: `nginx`, `nginx-access`, `mysql`, `auth`, `syslog`, `fail2ban`, `syamadmin`\n"
                f"Contoh: `/logs nginx 100`",
                parse_mode="Markdown",
            )
            return

        msg = await self._reply(update,f"📋 Mengambil {lines_n} baris log `{service}`...", parse_mode="Markdown")
        r = await self.modules["executor"].run(cmd, module="bot", check=False)
        await self._edit(msg,
            f"📋 *Log: {service}* (≤{lines_n} baris)\n```\n{r['stdout'][:3500]}\n```",
            parse_mode="Markdown",
        )

    async def cmd_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Kontrol layanan langsung: /service restart|stop|start|status <nama>."""
        if not await self._guard(update):
            return
        args = context.args or []
        valid_actions = ("restart", "stop", "start", "status", "reload")

        if len(args) < 2 or args[0].lower() not in valid_actions:
            await self._reply(update,
                "🔧 *Penggunaan /service:*\n"
                "`/service status <nama>` — cek status\n"
                "`/service restart <nama>` — restart\n"
                "`/service reload <nama>` — reload config\n"
                "`/service start <nama>` — start\n"
                "`/service stop <nama>` — stop (OTP)\n\n"
                f"Layanan umum: {', '.join(f'`{s}`' for s in MANAGED_SERVICES)}",
                parse_mode="Markdown",
            )
            return

        action = args[0].lower()
        service = args[1]
        # Validasi nama layanan agar aman (service_action lewat run_exec arg-list)
        if not re.match(r"^[a-zA-Z0-9@._\-]+$", service):
            await self._reply(update,"❌ Nama layanan tidak valid.", parse_mode="Markdown")
            return

        # stop = berpotensi outage → wajib OTP
        if action == "stop":
            otp = self._generate_otp()
            await self._reply(update,
                f"⚠️ *Konfirmasi Stop Layanan*\n\n"
                f"• Layanan: `{service}`\n"
                f"Menghentikan layanan dapat menyebabkan downtime.\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("service_stop", otp, 60, service=service)
            return

        msg = await self._reply(update,f"🔧 `{action}` layanan `{service}`...", parse_mode="Markdown")
        r = await self.modules["executor"].service_action(service, action)
        out = (r.get("stdout") or r.get("stderr") or "").strip()
        icon = "✅" if r.get("success") else "❌"
        await self._edit(msg,
            f"{icon} *{action} `{service}`*\n```\n{out[:3000] or '(tidak ada output)'}\n```",
            parse_mode="Markdown",
        )

    async def cmd_sysupdate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Update & upgrade paket OS via apt (OTP)."""
        if not await self._guard(update):
            return
        otp = self._generate_otp()
        await self._reply(update,
            "⚠️ *Update & Upgrade Paket OS*\n\n"
            "Akan menjalankan `apt-get update` lalu `apt-get upgrade -y`.\n"
            "Proses bisa memakan beberapa menit dan memperbarui paket sistem.\n\n"
            f"{self._otp_line(otp, 120)}",
            parse_mode="Markdown",
        )
        self._arm_confirmation("apt_upgrade", otp, 120)

    async def cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Self-update SyamAdmin dari GitHub: /update [check|now]."""
        if not await self._guard(update):
            return
        updater = self.modules.get("updater")
        if not updater:
            await self._reply(update, "❌ Modul updater tidak aktif.", parse_mode="Markdown")
            return
        args = context.args or []
        sub = args[0].lower() if args else "check"

        if sub in ("", "check", "cek"):
            msg = await self._reply(update, "🔎 Mengecek versi terbaru di GitHub...")
            res = await updater.check()
            if not res.get("ok"):
                await self._edit(msg, f"❌ Gagal cek update: {res.get('error')}", parse_mode="Markdown")
                return
            if res["update_available"]:
                await self._edit(msg,
                    f"⬆️ *Update SyamAdmin tersedia!*\n\n"
                    f"• Versi sekarang : `{res['local']}`\n"
                    f"• Versi terbaru  : `{res['remote']}`\n\n"
                    f"Ketik `/update now` untuk memasang (backup + auto-rollback, perlu OTP).",
                    parse_mode="Markdown",
                )
            else:
                await self._edit(msg,
                    f"✅ SyamAdmin sudah versi terbaru (`{res['local']}`).",
                    parse_mode="Markdown",
                )
            return

        if sub in ("now", "apply", "pasang", "upgrade"):
            res = await updater.check()
            local = res.get("local", "?")
            remote = res.get("remote", "?")
            if res.get("ok") and not res.get("update_available"):
                await self._reply(update,
                    f"✅ Sudah versi terbaru (`{local}`). Tidak ada yang perlu diupdate.\n"
                    f"_Paksa pasang ulang? Jalankan lagi `/update now` setelah ada rilis baru._",
                    parse_mode="Markdown",
                )
                return
            otp = self._generate_otp()
            await self._reply(update,
                f"⚠️ *Konfirmasi Update SyamAdmin*\n\n"
                f"• `{local}` → `{remote}`\n\n"
                f"Proses: backup → unduh dari GitHub → ganti file → restart → "
                f"health-check (auto-rollback bila gagal).\n"
                f"⏳ Bot akan restart sebentar; hasil akhir dikirim otomatis.\n\n"
                f"{self._otp_line(otp, 120)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("app_update", otp, 120, target=remote)
            return

        await self._reply(update,
            "🔄 *Penggunaan /update:*\n"
            "`/update` atau `/update check` — cek versi terbaru di GitHub\n"
            "`/update now` — pasang update (OTP)\n\n"
            "_Update paket OS (apt) ada di `/sysupdate`._",
            parse_mode="Markdown",
        )

    async def cmd_reboot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reboot server (OTP)."""
        if not await self._guard(update):
            return
        otp = self._generate_otp()
        await self._reply(update,
            "⚠️ *Konfirmasi Reboot Server*\n\n"
            "Server akan dimulai ulang. Semua layanan akan terputus sesaat "
            "dan bot tidak merespons hingga server kembali online.\n\n"
            f"{self._otp_line(otp, 120)}",
            parse_mode="Markdown",
        )
        self._arm_confirmation("reboot", otp, 120)

    async def cmd_audit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        msg = await self._reply(update,"📋 Memuat audit log...")
        entries = await self.modules["executor"].get_recent_audit(limit=15)
        if not entries:
            await self._edit(msg,"📭 Belum ada audit log.")
            return

        lines = ["📋 *Audit Log Terbaru*\n"]
        for e in entries:
            icon = "✅" if e["status"] == "success" else "❌"
            lines.append(f"{icon} `{e['timestamp']}` [{e['module']}] {e['action'][:60]}")

        await self._edit(msg,"\n".join(lines), parse_mode="Markdown")

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
                f"{self._otp_line(otp)}",
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

        # Konteks waktu sistem + profil admin/server (volatil → bukan di prompt cache)
        parts = []
        sys_ctx = brain.get_system_context()
        if sys_ctx:
            parts.append(sys_ctx)
        profile_ctx = brain.get_profile_context()
        if profile_ctx:
            parts.append(profile_ctx)
        parts.append(
            f"CPU: {metrics['cpu_percent']}%, RAM: {metrics['ram_percent']}%, "
            f"Disk: {metrics['disk_percent']}%, Load: {metrics['load_1']}, "
            f"Uptime: {metrics['uptime_str']}\n{state}"
        )
        context_str = "\n".join(parts)

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
                f"{self._otp_line(otp)}",
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
            f"{risk_note}\n\n{self._otp_line(otp, 120)}"
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
                    self._arm_confirmation("harden_all", otp, 120)
                    await self._reply(update,
                        f"🔐 Akan menjalankan hardening SSH + Fail2Ban + Firewall + Auto-update.\n"
                        f"{self._otp_line(otp, 120)}",
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
                self._arm_confirmation(
                    "wizard_provision", otp, 120,
                    domain=domain, framework=framework, db=need_db,
                )

                await self._reply(update,
                    f"📝 *Ringkasan Konfigurasi Website*\n\n"
                    f"• *Domain*: `{domain}`\n"
                    f"• *Framework/Platform*: `{framework}`\n"
                    f"• *Buat Database MySQL*: `{'Ya' if need_db else 'Tidak'}`\n\n"
                    f"⚠️ *Peringatan*: Proses ini akan mengubah konfigurasi Nginx dan Firewall.\n"
                    f"{self._otp_line(otp, 120)}",
                    parse_mode="Markdown"
                )
                return

            # Onboarding profil — tanya field PROFILE_FIELDS satu per satu
            elif state == "PROFILE":
                low = user_text.lower()
                if low in ("batal", "cancel"):
                    del self._wizard_states[self.admin_id]
                    await self._reply(update,"❌ Pengisian profil dibatalkan.", parse_mode="Markdown")
                    return

                idx = wizard["idx"]
                field = PROFILE_FIELDS[idx]
                if low in ("lewati", "skip", "-"):
                    if field["required"]:
                        await self._reply(update,
                            f"⚠️ Field ini wajib diisi.\n\n*{field['label']}*?\n_contoh: {field['example']}_",
                            parse_mode="Markdown",
                        )
                        return
                    # lewati: tidak menyimpan
                else:
                    wizard["data"][field["key"]] = user_text

                idx += 1
                wizard["idx"] = idx
                if idx < len(PROFILE_FIELDS):
                    nxt = PROFILE_FIELDS[idx]
                    opt = "" if nxt["required"] else " _(ketik `lewati` bila kosong)_"
                    await self._reply(update,
                        f"{idx + 1}️⃣ *{nxt['label']}*?{opt}\n_contoh: {nxt['example']}_",
                        parse_mode="Markdown",
                    )
                    return

                # Selesai — simpan semua, sapa personal
                data = wizard["data"]
                del self._wizard_states[self.admin_id]
                brain = self.modules["brain"]
                for k, v in data.items():
                    brain.set_profile_value(k, v)
                nick = brain.get_admin_nickname()
                filled = "\n".join(
                    f"• {f['label']}: `{data[f['key']]}`"
                    for f in PROFILE_FIELDS if f["key"] in data
                ) or "_(tidak ada yang diisi)_"
                await self._reply(update,
                    f"✅ *Profil tersimpan!* Salam kenal, *{nick}* 🤝\n\n{filled}\n\n"
                    "Mulai sekarang Jarwo akan menyapa & menyesuaikan konteks dengan profilmu.\n"
                    "_Ubah kapan saja: `/profile set <field> <nilai>` atau `/profile setup`._",
                    parse_mode="Markdown",
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

    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Profil admin & konteks server: /profile [setup|set <field> <nilai>|reset]."""
        if not await self._guard(update):
            return
        brain = self.modules["brain"]
        args = context.args or []
        sub = args[0].lower() if args else ""

        # Tampilkan profil saat ini
        if sub == "":
            prof = brain.get_profile()
            if not prof:
                await self._reply(update,
                    "👤 *Profil belum diisi.*\n\n"
                    "Biar Jarwo bisa lebih personal (sapa dengan nama, paham konteks server & "
                    "zona waktu kamu), yuk isi profil:\n"
                    "• `/profile setup` — wizard tanya-jawab langkah demi langkah\n"
                    "• `/profile set name Budi` — isi satu field saja",
                    parse_mode="Markdown",
                )
                return
            lines = ["👤 *Profil Admin & Konteks Server*\n"]
            for f in PROFILE_FIELDS:
                v = prof.get(f["key"])
                mark = f"`{v}`" if v else "_(kosong)_"
                lines.append(f"• {f['label']}: {mark}")
            lines.append("\n_Ubah: `/profile setup` · `/profile set <field> <nilai>` · `/profile reset`_")
            lines.append("Field: " + ", ".join(f"`{f['key']}`" for f in PROFILE_FIELDS))
            await self._reply(update, "\n".join(lines), parse_mode="Markdown")
            return

        # Wizard tanya-jawab
        if sub in ("setup", "wizard"):
            self._wizard_states[self.admin_id] = {
                "state": "PROFILE",
                "idx": 0,
                "data": {},
                "expires": datetime.now().timestamp() + 600,
            }
            first = PROFILE_FIELDS[0]
            await self._reply(update,
                "👋 *Kenalan dulu yuk!*\n\n"
                "Jarwo akan tanya beberapa hal singkat biar bisa melayani lebih personal.\n"
                "Ketik `lewati` untuk melompati pertanyaan opsional, atau `batal` untuk berhenti.\n\n"
                f"1️⃣ *{first['label']}*?\n_contoh: {first['example']}_",
                parse_mode="Markdown",
            )
            return

        # Set satu field
        if sub == "set":
            if len(args) < 3:
                await self._reply(update,
                    "❌ Format: `/profile set <field> <nilai>`\n"
                    "Field: " + ", ".join(f"`{f['key']}`" for f in PROFILE_FIELDS),
                    parse_mode="Markdown",
                )
                return
            key = args[1].lower()
            value = " ".join(args[2:])
            if brain.set_profile_value(key, value):
                await self._reply(update, f"✅ `{key}` = `{value}` tersimpan.", parse_mode="Markdown")
            else:
                await self._reply(update,
                    f"❌ Field `{key}` tidak dikenal.\n"
                    "Field valid: " + ", ".join(f"`{f['key']}`" for f in PROFILE_FIELDS),
                    parse_mode="Markdown",
                )
            return

        # Reset (konfirmasi ringan — bukan destruktif sistem, kata afirmatif OK)
        if sub == "reset":
            otp = self._generate_otp()
            await self._reply(update,
                "🗑️ *Reset Profil*\n\nSemua data profil admin & konteks server akan dihapus.\n\n"
                f"Balas `ya` atau `{otp}` untuk konfirmasi (berlaku 60 detik).",
                parse_mode="Markdown",
            )
            self._arm_confirmation("profile_reset", otp, 60)
            return

        await self._reply(update,
            "👤 *Penggunaan /profile:*\n"
            "`/profile` — lihat profil\n"
            "`/profile setup` — wizard tanya-jawab\n"
            "`/profile set <field> <nilai>` — isi satu field\n"
            "`/profile reset` — hapus profil",
            parse_mode="Markdown",
        )

    async def cmd_pefi(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PeFi — Pre-Emptive Firewall Agent command router."""
        if not await self._guard(update):
            return

        pefi = self.modules.get("pefi")
        if not pefi:
            await self._reply(update, "❌ Modul PeFi tidak aktif.", parse_mode="Markdown")
            return

        args = context.args or []
        sub = args[0].lower() if args else ""

        # ── Perintah informasi (tanpa OTP) ──────────────────────────────
        if sub == "" or sub == "status":
            msg = await self._reply(update, "🛡️ Mengambil status PeFi...")
            result = await pefi.get_status()
            await self._edit(msg, result, parse_mode="Markdown")

        elif sub == "threats":
            msg = await self._reply(update, "⏳ Memuat daftar ancaman...")
            result = await pefi.get_active_threats()
            await self._edit(msg, result, parse_mode="Markdown")

        elif sub == "rules":
            msg = await self._reply(update, "⏳ Memuat aturan aktif...")
            result = await pefi.get_active_rules()
            await self._edit(msg, result, parse_mode="Markdown")

        elif sub == "report":
            hours = int(args[1]) if len(args) > 1 and args[1].isdigit() else 24
            msg = await self._reply(update, f"📊 Menyusun laporan {hours} jam terakhir...")
            result = await pefi.get_report(hours=hours)
            await self._edit(msg, result, parse_mode="Markdown")

        elif sub == "health":
            msg = await self._reply(update, "🏥 Mengecek kesehatan sistem PeFi...")
            result = await pefi.get_health()
            await self._edit(msg, result, parse_mode="Markdown")

        # ── Perintah destructive/perubahan (wajib OTP) ──────────────────
        elif sub == "scan":
            otp = self._generate_otp()
            await self._reply(
                update,
                f"🛡️ *Konfirmasi PeFi Scan Manual*\n\n"
                f"Akan memicu satu siklus analisis traffic sekarang.\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("pefi_scan", otp, 60)

        elif sub == "block":
            if len(args) < 2:
                await self._reply(update, "❌ Format: `/pefi block <ip> [jam]`", parse_mode="Markdown")
                return
            ip = args[1]
            hours = int(args[2]) if len(args) > 2 and args[2].isdigit() else 24
            otp = self._generate_otp()
            await self._reply(
                update,
                f"🔒 *Konfirmasi Blokir IP*\n\n"
                f"• IP: `{ip}`\n"
                f"• Durasi: {hours} jam\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("pefi_block", otp, 60, ip=ip, hours=hours)

        elif sub == "unblock":
            if len(args) < 2:
                await self._reply(update, "❌ Format: `/pefi unblock <ip>`", parse_mode="Markdown")
                return
            ip = args[1]
            otp = self._generate_otp()
            await self._reply(
                update,
                f"🔓 *Konfirmasi Hapus Blokir*\n\n"
                f"• IP: `{ip}`\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("pefi_unblock", otp, 60, ip=ip)

        elif sub == "whitelist":
            if len(args) < 2:
                await self._reply(update, "❌ Format: `/pefi whitelist <ip>`", parse_mode="Markdown")
                return
            ip = args[1]
            reason = " ".join(args[2:]) if len(args) > 2 else "Ditambahkan manual oleh admin"
            otp = self._generate_otp()
            await self._reply(
                update,
                f"✅ *Konfirmasi Whitelist IP*\n\n"
                f"• IP: `{ip}`\n"
                f"• Alasan: {reason}\n\n"
                f"PeFi tidak akan memproses IP ini.\n{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("pefi_whitelist", otp, 60, ip=ip, reason=reason)

        elif sub == "ignore":
            if len(args) < 2 or not args[1].isdigit():
                await self._reply(update, "❌ Format: `/pefi ignore <threat_id>`", parse_mode="Markdown")
                return
            threat_id = int(args[1])
            otp = self._generate_otp()
            await self._reply(
                update,
                f"⬜ *Tandai Ancaman sebagai False Positive*\n\n"
                f"• Threat ID: `{threat_id}`\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("pefi_ignore", otp, 60, threat_id=threat_id)

        elif sub == "autoblock":
            if len(args) < 2 or args[1].lower() not in ("on", "off"):
                current = pefi.config.get("PEFI_AUTO_BLOCK", "false").lower()
                status = "🟢 ON" if current == "true" else "🔴 OFF"
                await self._reply(
                    update,
                    f"🤖 *PeFi Auto-Block*\n\nStatus saat ini: {status}\n\n"
                    f"Gunakan `/pefi autoblock on` atau `/pefi autoblock off`.",
                    parse_mode="Markdown",
                )
                return
            toggle = args[1].lower()
            otp = self._generate_otp()
            action_str = "MENGAKTIFKAN" if toggle == "on" else "MENONAKTIFKAN"
            await self._reply(
                update,
                f"⚠️ *Konfirmasi {action_str} Auto-Block*\n\n"
                f"{'Auto-block ON: ancaman HIGH/CRITICAL dengan confidence ≥ 95% diblokir TANPA konfirmasi admin.' if toggle == 'on' else 'Auto-block OFF: semua blokir butuh konfirmasi manual admin.'}\n\n"
                f"{self._otp_line(otp)}",
                parse_mode="Markdown",
            )
            self._arm_confirmation("pefi_autoblock", otp, 60, toggle=toggle)

        else:
            await self._reply(
                update,
                "❓ Sub-command tidak dikenal.\n\n"
                "Tersedia: `status` · `threats` · `rules` · `report` · `health` · `scan` · "
                "`block` · `unblock` · `whitelist` · `ignore` · `autoblock`\n\n"
                "Contoh: `/pefi threats` atau `/pefi block 1.2.3.4`",
                parse_mode="Markdown",
            )

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
            f"{self._otp_line(otp)}",
            parse_mode="Markdown",
        )
        self._arm_confirmation(
            "add_cron", otp, 60,
            cron_expression=res["cron_expression"],
            command=res["command"],
            readable_summary=res["readable_summary"],
        )

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
                f"{self._otp_line(otp)}"
            )
            self._arm_confirmation(
                "optimize_system", otp, 60,
                service=res.get("target_service"),
                command=res.get("optimization_command"),
            )
            
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

    async def _do_security_report(self, update: Update):
        """Laporan intelijen keamanan dari scan log (AI)."""
        msg = await self._reply(update,"⏳ Menganalisis log keamanan server...")
        report = await self.modules["security"].scan_auth_logs(brain=self.modules["brain"])
        await self._edit(msg,report, parse_mode="Markdown")

    async def _do_ssh_port(self, update: Update, args: list):
        """Ubah port SSH dengan verifikasi OTP."""
        if not args:
            await self._reply(update,
                "❌ Format salah. Gunakan: `/security ssh-port <PORT_BARU>` (rentang 1024 - 65535)",
                parse_mode="Markdown")
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
            f"{self._otp_line(otp, 120)}",
            parse_mode="Markdown"
        )
        self._arm_confirmation("change_ssh_port", otp, 120, new_port=new_port)

    async def cmd_security_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Alias: /security report (kompatibilitas mundur)."""
        if not await self._guard(update):
            return
        await self._do_security_report(update)

    async def cmd_harden_ssh_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Alias: /security ssh-port <port> (kompatibilitas mundur)."""
        if not await self._guard(update):
            return
        await self._do_ssh_port(update, context.args or [])

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

        elif action == "service_stop":
            svc = pending["service"]
            msg = await self._reply(update,f"🔧 Menghentikan layanan `{svc}`...", parse_mode="Markdown")
            r = await self.modules["executor"].service_action(svc, "stop")
            out = (r.get("stdout") or r.get("stderr") or "").strip()
            icon = "✅" if r.get("success") else "❌"
            await self._edit(msg,
                f"{icon} *stop `{svc}`*\n```\n{out[:3000] or '(tidak ada output)'}\n```",
                parse_mode="Markdown",
            )

        elif action == "apt_upgrade":
            msg = await self._reply(update,"⬆️ Menjalankan update & upgrade paket... (bisa beberapa menit)")
            r = await self.modules["executor"].run(
                "DEBIAN_FRONTEND=noninteractive apt-get update && "
                "DEBIAN_FRONTEND=noninteractive apt-get -y upgrade",
                module="system", timeout=600, check=False,
            )
            out = (r.get("stdout") or r.get("stderr") or "").strip()
            icon = "✅" if r.get("success") else "❌"
            await self._edit(msg,
                f"{icon} *Update & Upgrade Sistem*\n```\n{out[-3000:] or '(tidak ada output)'}\n```",
                parse_mode="Markdown",
            )

        elif action == "reboot":
            await self._reply(update,
                "🔁 *Server akan reboot sekarang.*\nBot tidak merespons hingga server kembali online.",
                parse_mode="Markdown",
            )
            await self.modules["executor"].run(
                "systemctl reboot || shutdown -r now",
                module="system", check=False,
            )

        elif action == "profile_reset":
            self.modules["brain"].clear_profile()
            await self._reply(update,
                "🗑️ Profil dihapus. Ketik `/profile setup` untuk mengisi ulang.",
                parse_mode="Markdown",
            )

        elif action == "app_update":
            updater = self.modules.get("updater")
            await self._reply(update,
                "🚀 *Update SyamAdmin dimulai...*\n"
                "Backup → unduh → ganti file → restart. Bot akan terputus sebentar; "
                "hasil akhir dikirim otomatis setelah online kembali.\n"
                "_Log: `/var/log/syamadmin/update.log`_",
                parse_mode="Markdown",
            )
            res = await updater.trigger_update()
            if not res.get("ok"):
                await self._reply(update,
                    f"❌ Gagal memicu updater: {res.get('error')}",
                    parse_mode="Markdown",
                )

        # ── PeFi actions ─────────────────────────────────────────────────
        elif action == "pefi_scan":
            pefi = self.modules.get("pefi")
            await self._reply(update, "🛡️ Menjalankan PeFi scan manual...")
            result = await pefi.scan_now()
            await self._reply(update, result, parse_mode="Markdown")

        elif action == "pefi_block":
            pefi = self.modules.get("pefi")
            ip = pending["ip"]
            hours = pending.get("hours", 24)
            await self._reply(update, f"🔒 Memblokir `{ip}`...", parse_mode="Markdown")
            result = await pefi.approve_block(ip, duration_hours=hours)
            await self._reply(update, result, parse_mode="Markdown")

        elif action == "pefi_unblock":
            pefi = self.modules.get("pefi")
            ip = pending["ip"]
            await self._reply(update, f"🔓 Menghapus blokir `{ip}`...", parse_mode="Markdown")
            result = await pefi.remove_rule(ip)
            await self._reply(update, result, parse_mode="Markdown")

        elif action == "pefi_whitelist":
            pefi = self.modules.get("pefi")
            ip = pending["ip"]
            reason = pending.get("reason", "Manual oleh admin")
            result = await pefi.whitelist_ip(ip, reason=reason)
            await self._reply(update, result, parse_mode="Markdown")

        elif action == "pefi_ignore":
            pefi = self.modules.get("pefi")
            threat_id = pending["threat_id"]
            result = await pefi.ignore_threat(threat_id)
            await self._reply(update, result, parse_mode="Markdown")

        elif action == "pefi_autoblock":
            pefi = self.modules.get("pefi")
            toggle = pending["toggle"]
            pefi.config["PEFI_AUTO_BLOCK"] = "true" if toggle == "on" else "false"
            status = "🟢 AKTIF" if toggle == "on" else "🔴 NONAKTIF"
            await self._reply(
                update,
                f"✅ *Auto-Block PeFi: {status}*\n\n"
                f"{'IP dengan threat HIGH/CRITICAL dan confidence ≥95% akan diblokir otomatis.' if toggle == 'on' else 'Semua blokir kini butuh konfirmasi manual admin.'}\n\n"
                f"_Pengaturan aktif langsung, tidak perlu restart._",
                parse_mode="Markdown",
            )

    async def run(self):
        """Start the Telegram bot."""
        logger.info("Starting Telegram bot...")

        self._app = Application.builder().token(self.token).build()
        app = self._app

        # Register command handlers dari registry tunggal (anti-drift)
        for _title, entries in COMMAND_REGISTRY:
            for cmd, handler, *_rest in entries:
                app.add_handler(CommandHandler(cmd, getattr(self, handler)))
        for cmd, handler in COMMAND_ALIASES:
            app.add_handler(CommandHandler(cmd, getattr(self, handler)))

        # Free-text handler (last)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Set bot commands menu (juga dari registry)
        await app.bot.set_my_commands(_build_menu_commands())

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
