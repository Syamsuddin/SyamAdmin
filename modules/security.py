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

        await self.notifier.send(msg)
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
        await self.notifier.send(msg)
        return msg

    async def audit(self) -> str:
        """Run a comprehensive security audit."""
        await self.notifier.send("🔍 *Running security audit...*")
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
        await self.notifier.send(report)
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
