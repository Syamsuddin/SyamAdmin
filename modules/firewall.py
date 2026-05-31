"""
FirewallManager — UFW firewall rule management.
"""

import logging
import os

logger = logging.getLogger("syamadmin.firewall")


class FirewallManager:
    """Manage UFW firewall rules."""

    def __init__(self, executor, notifier):
        self.executor = executor
        self.notifier = notifier
        self.ssh_port = int(os.environ.get("SSH_PORT", 22))

    async def setup_defaults(self) -> str:
        """Initialize UFW with sensible defaults for LEMP stack."""
        await self.notifier.send("🧱 *Setting up firewall defaults...*")

        commands = [
            "ufw --force reset",
            "ufw default deny incoming",
            "ufw default allow outgoing",
            f"ufw allow {self.ssh_port}/tcp comment 'SSH'",
            "ufw allow 80/tcp comment 'HTTP'",
            "ufw allow 443/tcp comment 'HTTPS'",
            "ufw --force enable",
        ]

        for cmd in commands:
            r = await self.executor.run(cmd, module="firewall")
            if not r["success"]:
                return f"❌ Firewall setup gagal pada: `{cmd}`\n{r['stderr'][:300]}"

        return await self.status()

    async def status(self) -> str:
        """Get current firewall status and rules."""
        r = await self.executor.run("ufw status verbose", module="firewall")
        return f"🧱 *Firewall Status*\n```\n{r['stdout'][:3000]}\n```"

    async def allow_port(self, port: str, protocol: str = "tcp", comment: str = "") -> str:
        """Allow incoming traffic on a port."""
        cmd = f"ufw allow {port}/{protocol}"
        if comment:
            cmd += f" comment '{comment}'"

        r = await self.executor.run(cmd, module="firewall")
        if r["success"]:
            return f"✅ Port `{port}/{protocol}` dibuka. {comment}"
        return f"❌ Gagal membuka port: {r['stderr'][:300]}"

    async def deny_port(self, port: str, protocol: str = "tcp") -> str:
        """Block incoming traffic on a port."""
        r = await self.executor.run(f"ufw deny {port}/{protocol}", module="firewall")
        if r["success"]:
            return f"🚫 Port `{port}/{protocol}` diblokir."
        return f"❌ Gagal memblokir port: {r['stderr'][:300]}"

    async def delete_rule(self, rule_number: int) -> str:
        """Delete a firewall rule by number."""
        r = await self.executor.run(
            f"echo 'y' | ufw delete {rule_number}", module="firewall"
        )
        if r["success"]:
            return f"✅ Rule #{rule_number} dihapus."
        return f"❌ Gagal menghapus rule: {r['stderr'][:300]}"

    async def allow_ip(self, ip: str, comment: str = "") -> str:
        """Allow all traffic from a specific IP."""
        cmd = f"ufw allow from {ip}"
        if comment:
            cmd += f" comment '{comment}'"
        r = await self.executor.run(cmd, module="firewall")
        if r["success"]:
            return f"✅ IP `{ip}` diizinkan. {comment}"
        return f"❌ Gagal: {r['stderr'][:300]}"

    async def deny_ip(self, ip: str) -> str:
        """Block all traffic from a specific IP."""
        r = await self.executor.run(f"ufw deny from {ip}", module="firewall")
        if r["success"]:
            return f"🚫 IP `{ip}` diblokir."
        return f"❌ Gagal: {r['stderr'][:300]}"

    async def list_rules(self) -> str:
        """List all rules with numbers."""
        r = await self.executor.run("ufw status numbered", module="firewall")
        return f"🧱 *Firewall Rules*\n```\n{r['stdout'][:3000]}\n```"

    async def rate_limit(self, port: str = "") -> str:
        """Enable rate limiting on a port (default: SSH)."""
        target = port or str(self.ssh_port)
        r = await self.executor.run(
            f"ufw limit {target}/tcp comment 'Rate limited'",
            module="firewall",
        )
        if r["success"]:
            return f"✅ Rate limiting aktif pada port `{target}`."
        return f"❌ Gagal: {r['stderr'][:300]}"
