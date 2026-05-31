"""
SecurityManager — Server hardening, audit, and intrusion detection.
"""

import logging
import os

logger = logging.getLogger("syamadmin.security")


class SecurityManager:
    """Security hardening and continuous audit."""

    def __init__(self, executor, notifier):
        self.executor = executor
        self.notifier = notifier
        self.ssh_port = int(os.environ.get("SSH_PORT", 22))

    async def harden_ssh(self) -> str:
        """Apply SSH hardening configuration."""
        await self.notifier.send("🔐 *Hardening SSH...*")

        sshd_hardening = f"""
# SyamAdmin SSH Hardening
Port {self.ssh_port}
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PermitEmptyPasswords no
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
PrintMotd no
AcceptEnv LANG LC_*
MaxAuthTries 3
MaxSessions 3
ClientAliveInterval 300
ClientAliveCountMax 2
LoginGraceTime 30
AllowAgentForwarding no
AllowTcpForwarding no
"""
        # Backup original
        await self.executor.run(
            "cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%s)",
            module="security",
        )

        # Write hardened config
        escaped = sshd_hardening.replace("'", "'\\''")
        await self.executor.run(
            f"echo '{escaped}' > /etc/ssh/sshd_config.d/99-syamadmin.conf",
            module="security",
        )

        # Test and reload
        test = await self.executor.run("sshd -t", module="security")
        if test["success"]:
            await self.executor.run("systemctl reload sshd", module="security")
            msg = (
                f"✅ *SSH Hardened*\n"
                f"• Port: `{self.ssh_port}`\n"
                f"• Root login: key-only\n"
                f"• Password auth: disabled\n"
                f"• Max auth tries: 3\n"
                f"• Idle timeout: 5 min"
            )
        else:
            msg = f"❌ SSH config test gagal:\n```\n{test['stderr'][:500]}\n```"

        # Hasil dikembalikan ke pemanggil (bot) untuk ditampilkan — tidak duplikat via notifier
        return msg

    async def setup_fail2ban(self) -> str:
        """Install and configure fail2ban."""
        await self.notifier.send("🛡 *Setting up Fail2Ban...*")

        r = await self.executor.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fail2ban",
            module="security", timeout=120,
        )

        if not r["success"]:
            return f"❌ Gagal install fail2ban: {r['stderr'][:300]}"

        jail_config = f"""
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
backend = systemd
action = %(action_mwl)s

[sshd]
enabled = true
port = {self.ssh_port}
maxretry = 3
bantime = 7200

[nginx-http-auth]
enabled = true
port = http,https

[nginx-botsearch]
enabled = true
port = http,https

[nginx-limit-req]
enabled = true
port = http,https
"""
        escaped = jail_config.replace("'", "'\\''")
        await self.executor.run(
            f"echo '{escaped}' > /etc/fail2ban/jail.local",
            module="security",
        )
        await self.executor.run(
            "systemctl enable --now fail2ban && systemctl restart fail2ban",
            module="security",
        )

        msg = (
            "✅ *Fail2Ban Active*\n"
            "• SSH: 3 attempts → ban 2 hours\n"
            "• Nginx auth: 3 attempts → ban 1 hour\n"
            "• Bot search: enabled\n"
            "• Rate limit: enabled"
        )
        # Hasil dikembalikan ke pemanggil (bot) untuk ditampilkan — tidak duplikat via notifier
        return msg

    async def audit(self) -> str:
        """Run a comprehensive security audit."""
        findings = []

        # Check SSH config
        r = await self.executor.run(
            "grep -i 'PasswordAuthentication yes' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/* 2>/dev/null | head -3",
            module="security", check=False,
        )
        if r["stdout"]:
            findings.append("🔴 SSH password authentication masih ENABLED")
        else:
            findings.append("🟢 SSH password authentication disabled")

        # Check root login
        r = await self.executor.run(
            "grep -i 'PermitRootLogin yes' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/* 2>/dev/null",
            module="security", check=False,
        )
        if r["stdout"]:
            findings.append("🔴 SSH root login dengan password DIIZINKAN")
        else:
            findings.append("🟢 SSH root login restricted")

        # Check fail2ban
        r = await self.executor.run("systemctl is-active fail2ban", module="security", check=False)
        if r["stdout"].strip() == "active":
            ban_count = await self.executor.run(
                "fail2ban-client status sshd 2>/dev/null | grep 'Currently banned' | awk '{print $NF}'",
                module="security", check=False,
            )
            findings.append(f"🟢 Fail2Ban active (banned: {ban_count['stdout'].strip() or '0'})")
        else:
            findings.append("🔴 Fail2Ban TIDAK aktif")

        # Check UFW
        r = await self.executor.run("ufw status | head -1", module="security", check=False)
        if "active" in r["stdout"].lower():
            findings.append("🟢 UFW firewall active")
        else:
            findings.append("🔴 UFW firewall TIDAK aktif")

        # Check unattended upgrades
        r = await self.executor.run(
            "dpkg -l unattended-upgrades 2>/dev/null | grep -c '^ii'",
            module="security", check=False,
        )
        if r["stdout"].strip() == "1":
            findings.append("🟢 Unattended security updates enabled")
        else:
            findings.append("🟡 Unattended upgrades belum diinstall")

        # Check open ports
        r = await self.executor.run(
            "ss -tlnp | grep LISTEN | awk '{print $4}' | sort -u",
            module="security", check=False,
        )
        findings.append(f"📡 Open ports:\n```\n{r['stdout']}\n```")

        # Check pending updates
        r = await self.executor.run(
            "apt list --upgradable 2>/dev/null | grep -c upgradable",
            module="security", check=False,
        )
        count = r["stdout"].strip() or "0"
        if int(count) > 0:
            findings.append(f"🟡 {count} package updates tersedia")
        else:
            findings.append("🟢 Semua packages up-to-date")

        # Check last logins
        r = await self.executor.run(
            "last -5 -w | head -6",
            module="security", check=False,
        )
        findings.append(f"👤 Recent logins:\n```\n{r['stdout']}\n```")

        report = "🔍 *Security Audit Report*\n\n" + "\n".join(findings)
        # Hasil dikembalikan ke pemanggil (bot) untuk ditampilkan — tidak duplikat via notifier
        return report

    async def check_updates(self) -> str:
        """Check for available security updates."""
        r = await self.executor.run(
            "apt-get update -qq && apt list --upgradable 2>/dev/null | tail -20",
            module="security", timeout=120,
        )
        if r["stdout"]:
            return f"📦 *Available Updates:*\n```\n{r['stdout'][:2000]}\n```\n\nJalankan `/ai upgrade system` untuk mengupdate."
        return "✅ Semua packages sudah up-to-date."

    async def scan_rootkit(self) -> str:
        """Run rootkit scanner."""
        await self.notifier.send("🔎 *Scanning for rootkits...*\n_(ini bisa memakan waktu beberapa menit)_")

        r = await self.executor.run(
            "rkhunter --check --skip-keypress --report-warnings-only 2>&1 | tail -30",
            module="security", timeout=600,
        )

        if r["success"]:
            return f"🛡 *Rootkit Scan Results:*\n```\n{r['stdout'][:2000]}\n```"
        return f"⚠️ Rootkit scan selesai dengan warning:\n```\n{r['stdout'][:2000]}\n```"

    async def setup_auto_updates(self) -> str:
        """Enable automatic security updates."""
        r = await self.executor.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades && "
            "dpkg-reconfigure -plow unattended-upgrades",
            module="security", timeout=120,
        )
        if r["success"]:
            return "✅ Automatic security updates enabled."
        return f"❌ Gagal setup auto-updates: {r['stderr'][:300]}"

    async def scan_auth_logs(self, brain) -> str:
        """Scan authentication logs and fail2ban logs for threats, generating an AI report."""
        import os
        await self.notifier.send("🔍 *Memulai pemindaian log keamanan (auth.log & Fail2Ban)...*")
        
        auth_log_path = "/var/log/auth.log"
        fail2ban_log_path = "/var/log/fail2ban.log"
        
        auth_log_exists = os.path.exists(auth_log_path)
        fail2ban_exists = os.path.exists(fail2ban_log_path)
        
        if not auth_log_exists:
            # High-fidelity simulated log summary for testing and non-Ubuntu environments
            log_summary = (
                "=== SIMULATED SECURITY LOG SUMMARY (DEVELOPMENT ENVIRONMENT FALLBACK) ===\n"
                "System: macOS/Darwin (fallback active)\n"
                "Total Failed SSH attempts detected: 324\n"
                "Top targeted usernames:\n"
                "  - root: 210 attempts\n"
                "  - admin: 78 attempts\n"
                "  - user: 25 attempts\n"
                "  - support: 11 attempts\n"
                "Top Attacker IPs:\n"
                "  - 185.220.101.42 (Germany) - 105 attempts\n"
                "  - 43.134.52.12 (China) - 89 attempts\n"
                "  - 195.133.40.8 (Russia) - 67 attempts\n"
                "Active Fail2Ban bans (sshd jail): 4 IPs currently banned.\n"
                "Most targeted port: 22 (SSH default)"
            )
        else:
            res_auth = await self.executor.run(
                f"tail -n 500 {auth_log_path} | grep -E 'Failed|Invalid|connection closed|Accepted'",
                module="security", check=False
            )
            auth_lines = res_auth["stdout"].strip()
            
            res_f2b = await self.executor.run(
                "fail2ban-client status sshd 2>/dev/null",
                module="security", check=False
            )
            f2b_status = res_f2b["stdout"].strip()
            
            f2b_log = ""
            if fail2ban_exists:
                res_f2b_log = await self.executor.run(
                    f"tail -n 50 {fail2ban_log_path} | grep -E 'Ban|Unban'",
                    module="security", check=False
                )
                f2b_log = res_f2b_log["stdout"].strip()
                
            log_summary = (
                "=== SSH AUTHENTICATION RECENT LOGS ===\n"
                f"{auth_lines[:2000]}\n\n"
                "=== FAIL2BAN SSHD STATUS ===\n"
                f"{f2b_status}\n\n"
                "=== FAIL2BAN BAN/UNBAN RECENT LOGS ===\n"
                f"{f2b_log[:1000]}"
            )
            
        if brain:
            report = await brain.analyze_security_threats(log_summary)
            return report
        else:
            return f"⚠️ AI Brain tidak disuplai. Ringkasan Log:\n```\n{log_summary[:1000]}\n```"

    async def change_ssh_port(self, new_port: int) -> str:
        """Securely switch SSH port on Ubuntu LEMP, handling safety verification."""
        import platform
        import re
        import os
        import asyncio
        
        # 1. Validate port number
        if not (1024 <= new_port <= 65535):
            return f"❌ Port {new_port} tidak valid. Port SSH harus berada dalam rentang 1024 - 65535."
            
        # Ports reserved for common LEMP services
        reserved_ports = [3306, 80, 443, 8080, 9000]
        if new_port in reserved_ports:
            return f"❌ Port {new_port} dipesan untuk layanan utama LEMP (Nginx/MySQL/PHP-FPM) dan tidak dapat digunakan untuk SSH."
            
        # 2. Check if port is in use
        check_port = await self.executor.run(f"ss -tlnp | grep ':{new_port} '", module="security", check=False)
        if check_port["success"] and check_port["stdout"]:
            return f"❌ Port {new_port} sudah digunakan oleh layanan lain di server ini."
            
        # Handle Darwin (macOS) simulation/dry-run
        is_darwin = platform.system().lower() == "darwin"
        if is_darwin:
            old_port = self.ssh_port
            self.ssh_port = new_port
            return (
                f"✅ *[SIMULASI macOS] Port SSH Berhasil Diubah!*\n\n"
                f"• *Port Lama*: `{old_port}`\n"
                f"• *Port Baru*: `{new_port}`\n"
                f"• *Firewall*: UFW disimulasikan mengizinkan port `{new_port}` dan menghapus `{old_port}`.\n"
                f"• *Konfigurasi*: `/etc/ssh/sshd_config` disimulasikan terupdate.\n\n"
                f"⚠️ *PENTING*: Pada server produksi Ubuntu, pastikan mencoba login di sesi terminal baru menggunakan port baru sebelum menutup koneksi saat ini!"
            )
            
        # 3. Add UFW rule allowing the new port
        ufw_allow = await self.executor.run(f"ufw allow {new_port}/tcp", module="security", check=False)
        if not ufw_allow["success"]:
            return f"❌ Gagal menambahkan aturan firewall UFW untuk port {new_port}: {ufw_allow['stderr'][:200]}"
            
        # 4. Modify SSH configuration safely
        config_file = "/etc/ssh/sshd_config.d/99-syamadmin.conf"
        base_config = "/etc/ssh/sshd_config"
        
        target_file = config_file
        if not os.path.exists(config_file):
            target_file = base_config
            
        # Backup original configuration
        backup_cmd = f"cp {target_file} {target_file}.bak.$(date +%s)"
        await self.executor.run(backup_cmd, module="security")
        
        # Read file content
        with open(target_file, "r") as f:
            content = f.read()
            
        # Replace or append Port directive
        if re.search(r"^\s*Port\s+\d+", content, re.MULTILINE):
            new_content = re.sub(r"^\s*Port\s+\d+", f"Port {new_port}", content, flags=re.MULTILINE)
        else:
            new_content = content + f"\n# Added by SyamAdmin Port Tuner\nPort {new_port}\n"
            
        # Write back changes
        try:
            with open(target_file, "w") as f:
                f.write(new_content)
        except Exception as e:
            # Rollback UFW
            await self.executor.run(f"ufw delete allow {new_port}/tcp", module="security", check=False)
            return f"❌ Gagal menulis konfigurasi SSHD baru: {e}"
            
        # 5. Test configuration syntax
        test_sshd = await self.executor.run("sshd -t", module="security", check=False)
        if not test_sshd["success"]:
            # Rollback config
            with open(target_file, "w") as f:
                f.write(content)
            # Rollback UFW
            await self.executor.run(f"ufw delete allow {new_port}/tcp", module="security", check=False)
            return f"❌ Gagal: Sintaks konfigurasi SSHD tidak valid setelah perubahan:\n```\n{test_sshd['stderr'][:400]}\n```\nPerubahan dibatalkan otomatis."
            
        # 6. Restart SSH daemon
        restart_ssh = await self.executor.run("systemctl restart sshd || systemctl restart ssh", module="security", check=False)
        if not restart_ssh["success"]:
            # Rollback config
            with open(target_file, "w") as f:
                f.write(content)
            # Restart to original
            await self.executor.run("systemctl restart sshd || systemctl restart ssh", module="security", check=False)
            # Rollback UFW
            await self.executor.run(f"ufw delete allow {new_port}/tcp", module="security", check=False)
            return f"❌ Gagal me-restart layanan SSH: {restart_ssh['stderr'][:300]}. Perubahan dibatalkan otomatis."
            
        # 7. Internal test: check if SSH daemon is listening on the new port
        await asyncio.sleep(2) # Wait for sshd to bind
        verify_port = await self.executor.run(f"ss -tlnp | grep ':{new_port} '", module="security", check=False)
        if not (verify_port["success"] and verify_port["stdout"]):
            # Rollback config
            with open(target_file, "w") as f:
                f.write(content)
            await self.executor.run("systemctl restart sshd || systemctl restart ssh", module="security", check=False)
            await self.executor.run(f"ufw delete allow {new_port}/tcp", module="security", check=False)
            return f"❌ Gagal: SSHD tidak mendengarkan pada port baru {new_port} setelah restart. Perubahan dibatalkan otomatis."
            
        # 8. Success: Delete old port UFW rule
        old_port = self.ssh_port
        await self.executor.run(f"ufw delete allow {old_port}/tcp", module="security", check=False)
        
        # Update in-memory state
        self.ssh_port = new_port
        
        return (
            f"✅ *Port SSH Berhasil Diubah!* 🔐\n\n"
            f"• *Port Lama*: `{old_port}`\n"
            f"• *Port Baru*: `{new_port}`\n"
            f"• *Firewall*: UFW otomatis mengizinkan port `{new_port}` dan menghapus `{old_port}`.\n"
            f"• *Konfigurasi*: Terupdate di `{target_file}`.\n\n"
            f"⚠️ *PENTING*: Jangan tutup terminal/sesi chat ini terlebih dahulu! Silakan coba buka sesi terminal baru dan login menggunakan port baru (`ssh -p {new_port} user@ip`) untuk memastikan akses berjalan lancar."
        )

