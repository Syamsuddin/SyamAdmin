"""
SystemMonitor — Real-time server health monitoring.
Tracks CPU, RAM, disk, load, services, and network.
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime

import psutil

logger = logging.getLogger("syamadmin.monitor")

MANAGED_SERVICES = ["nginx", "mysql", "php8.3-fpm", "fail2ban", "ufw", "ssh"]


class SystemMonitor:
    """Continuous system monitoring with threshold alerts."""

    def __init__(self, notifier, executor, db_path: str, interval: int = 60, thresholds: dict = None):
        self.notifier = notifier
        self.executor = executor
        self.db_path = db_path
        self.interval = interval
        self.thresholds = thresholds or {
            "cpu": 85, "ram": 90, "disk": 85, "load": 4.0
        }
        self._running = False

    async def run_loop(self):
        """Main monitoring loop."""
        self._running = True
        logger.info(f"Monitor started (interval={self.interval}s)")

        while self._running:
            try:
                metrics = await self.collect_metrics()
                await self._store_metrics(metrics)
                await self._check_thresholds(metrics)
                await self._check_services()
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            await asyncio.sleep(self.interval)

    async def collect_metrics(self) -> dict:
        """Collect all system metrics."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        load_1, load_5, load_15 = psutil.getloadavg()
        net = psutil.net_io_counters()
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        return {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": cpu_percent,
            "cpu_count": psutil.cpu_count(),
            "ram_total_gb": round(memory.total / (1024 ** 3), 1),
            "ram_used_gb": round(memory.used / (1024 ** 3), 1),
            "ram_percent": memory.percent,
            "disk_total_gb": round(disk.total / (1024 ** 3), 1),
            "disk_used_gb": round(disk.used / (1024 ** 3), 1),
            "disk_percent": disk.percent,
            "load_1": round(load_1, 2),
            "load_5": round(load_5, 2),
            "load_15": round(load_15, 2),
            "net_sent_mb": round(net.bytes_sent / (1024 ** 2), 1),
            "net_recv_mb": round(net.bytes_recv / (1024 ** 2), 1),
            "uptime_days": uptime.days,
            "uptime_str": f"{uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m",
            "processes": len(psutil.pids()),
        }

    async def get_status_report(self) -> str:
        """Generate formatted status report for Telegram."""
        m = await self.collect_metrics()

        cpu_bar = self._progress_bar(m["cpu_percent"])
        ram_bar = self._progress_bar(m["ram_percent"])
        disk_bar = self._progress_bar(m["disk_percent"])

        return (
            f"🖥 *Server Status*\n"
            f"⏱ Uptime: `{m['uptime_str']}`\n\n"
            f"*CPU* {cpu_bar} `{m['cpu_percent']}%`\n"
            f"Cores: {m['cpu_count']} | Load: `{m['load_1']}/{m['load_5']}/{m['load_15']}`\n\n"
            f"*RAM* {ram_bar} `{m['ram_percent']}%`\n"
            f"Used: `{m['ram_used_gb']}/{m['ram_total_gb']} GB`\n\n"
            f"*Disk* {disk_bar} `{m['disk_percent']}%`\n"
            f"Used: `{m['disk_used_gb']}/{m['disk_total_gb']} GB`\n\n"
            f"*Network*\n"
            f"↑ Sent: `{m['net_sent_mb']} MB` | ↓ Recv: `{m['net_recv_mb']} MB`\n"
            f"Processes: `{m['processes']}`"
        )

    async def get_services_status(self) -> str:
        """Check status of all managed services."""
        lines = ["🔧 *Service Status*\n"]

        for svc in MANAGED_SERVICES:
            result = await self.executor.run(
                f"systemctl is-active {svc} 2>/dev/null || echo 'inactive'",
                module="monitor",
                check=False,
            )
            status = result["stdout"].strip()
            if status == "active":
                icon = "🟢"
            elif status == "inactive":
                icon = "⚫"
            else:
                icon = "🔴"
            lines.append(f"{icon} `{svc}`: {status}")

        return "\n".join(lines)

    async def _check_thresholds(self, metrics: dict):
        """Check if any metric exceeds threshold and alert."""
        if metrics["cpu_percent"] > self.thresholds["cpu"]:
            # Get top CPU processes
            top = await self.executor.run(
                "ps aux --sort=-%cpu | head -6 | awk '{print $11, $3\"%\"}'",
                module="monitor", check=False,
            )
            await self.notifier.alert(
                "warning", "monitor",
                f"CPU tinggi: *{metrics['cpu_percent']}%*\n"
                f"Top proses:\n```\n{top['stdout']}\n```"
            )

        if metrics["ram_percent"] > self.thresholds["ram"]:
            await self.notifier.alert(
                "warning", "monitor",
                f"RAM tinggi: *{metrics['ram_percent']}%* "
                f"({metrics['ram_used_gb']}/{metrics['ram_total_gb']} GB)"
            )

        if metrics["disk_percent"] > self.thresholds["disk"]:
            await self.notifier.alert(
                "critical", "monitor",
                f"Disk hampir penuh: *{metrics['disk_percent']}%* "
                f"({metrics['disk_used_gb']}/{metrics['disk_total_gb']} GB)"
            )

        if metrics["load_1"] > self.thresholds["load"]:
            await self.notifier.alert(
                "warning", "monitor",
                f"Load average tinggi: *{metrics['load_1']}* "
                f"(threshold: {self.thresholds['load']})"
            )

    async def _check_services(self):
        """Alert if any managed service is down."""
        for svc in MANAGED_SERVICES:
            result = await self.executor.run(
                f"systemctl is-active {svc} 2>/dev/null",
                module="monitor", check=False,
            )
            if result["stdout"].strip() not in ("active", ""):
                # Check if the service exists first
                exists = await self.executor.run(
                    f"systemctl list-unit-files {svc}.service | grep -c {svc}",
                    module="monitor", check=False,
                )
                if exists["stdout"].strip() != "0":
                    await self.notifier.alert(
                        "critical", "monitor",
                        f"Service *{svc}* is DOWN!\n"
                        f"Status: `{result['stdout'].strip()}`\n"
                        f"Jalankan `/ai restart {svc}` untuk restart.",
                        cooldown=True,
                    )

    async def _store_metrics(self, metrics: dict):
        """Store metrics in database for trend analysis."""
        try:
            conn = sqlite3.connect(self.db_path)
            for key in ("cpu_percent", "ram_percent", "disk_percent", "load_1"):
                conn.execute(
                    "INSERT INTO metrics (metric_type, value) VALUES (?, ?)",
                    (key, metrics[key]),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Metrics store error: {e}")

    @staticmethod
    def _progress_bar(percent: float, width: int = 10) -> str:
        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"`[{bar}]`"
