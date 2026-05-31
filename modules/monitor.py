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

    def __init__(self, notifier, executor, db_path: str, interval: int = 60, thresholds: dict = None, brain=None):
        self.notifier = notifier
        self.executor = executor
        self.db_path = db_path
        self.interval = interval
        self.thresholds = thresholds or {
            "cpu": 85, "ram": 90, "disk": 85, "load": 4.0
        }
        self._running = False
        self.brain = brain
        # Cache untuk state context (Fase 5)
        self._state_cache = None
        self._state_cache_ts = 0

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
                f"Top proses:\n```\n{top['stdout']}\n```",
                dedup_key="cpu_high",
            )

        if metrics["ram_percent"] > self.thresholds["ram"]:
            await self.notifier.alert(
                "warning", "monitor",
                f"RAM tinggi: *{metrics['ram_percent']}%* "
                f"({metrics['ram_used_gb']}/{metrics['ram_total_gb']} GB)",
                dedup_key="ram_high",
            )

        if metrics["disk_percent"] > self.thresholds["disk"]:
            await self.notifier.alert(
                "critical", "monitor",
                f"Disk hampir penuh: *{metrics['disk_percent']}%* "
                f"({metrics['disk_used_gb']}/{metrics['disk_total_gb']} GB)",
                dedup_key="disk_high",
            )

        if metrics["load_1"] > self.thresholds["load"]:
            await self.notifier.alert(
                "warning", "monitor",
                f"Load average tinggi: *{metrics['load_1']}* "
                f"(threshold: {self.thresholds['load']})",
                dedup_key="load_high",
            )

    async def _check_single_service(self, svc: str):
        """Periksa satu service dan kirim alert jika down."""
        result = await self.executor.run(
            f"systemctl is-active {svc} 2>/dev/null",
            module="monitor", check=False,
        )
        status_text = result["stdout"].strip()
        if status_text not in ("active", ""):
            # Pastikan service memang terdaftar di sistem
            exists = await self.executor.run(
                f"systemctl list-unit-files {svc}.service | grep -c {svc}",
                module="monitor", check=False,
            )
            if exists["stdout"].strip() != "0":
                log_paths = {
                    "nginx": "/var/log/nginx/error.log",
                    "mysql": "/var/log/mysql/error.log",
                    "fail2ban": "/var/log/fail2ban.log",
                }
                path = log_paths.get(svc, f"/var/log/{svc}.log")
                log_res = await self.executor.run(
                    f"tail -n 25 {path} 2>/dev/null || journalctl -u {svc} -n 25 --no-pager",
                    module="monitor", check=False
                )
                log_content = log_res["stdout"].strip() or "No recent logs found."

                diagnose_msg = ""
                if self.brain and self.brain.enabled:
                    diag = await self.brain.diagnose_crash(svc, log_content)
                    diagnose_msg = (
                        f"\n\n🧠 *Analisis Masalah (AI)*:\n"
                        f"• *Penyebab*: {diag.get('cause')}\n"
                        f"• *Solusi*: {diag.get('solution')}\n"
                        f"• *Risiko*: {diag.get('risk')}\n\n"
                        f"👉 Kirim perintah `/ai perbaiki {svc}` untuk memicu perbaikan otomatis via AI."
                    )
                else:
                    diagnose_msg = f"\n\nJalankan `/ai restart {svc}` untuk mencoba menyalakan kembali."

                await self.notifier.alert(
                    "critical", "monitor",
                    f"🚨 *Layanan DOWN: {svc}*!\n"
                    f"Status: `{status_text}`"
                    f"{diagnose_msg}",
                    cooldown=True,
                    dedup_key=f"service_down:{svc}",
                )

    async def _check_services(self):
        """Alert if any managed service is down — semua service dicek secara paralel."""
        await asyncio.gather(
            *[self._check_single_service(svc) for svc in MANAGED_SERVICES],
            return_exceptions=True,
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

    async def get_historical_summary(self, days: int = 7) -> str:
        """Fetch and aggregate metrics from database over the last N days."""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            # Fetch average and peak CPU, RAM, Disk, Load
            cur = conn.execute("""
                SELECT 
                    metric_type, 
                    AVG(value) as avg_val, 
                    MAX(value) as max_val 
                FROM metrics 
                WHERE timestamp >= datetime('now', ?) 
                GROUP BY metric_type
            """, (f"-{days} days",))
            rows = cur.fetchall()
            conn.close()
            
            if not rows:
                return "Belum ada data historis terkumpul."
                
            summary = [f"📊 *Summary Penggunaan {days} Hari Terakhir:*"]
            for r in rows:
                metric_type, avg_val, max_val = r
                name_map = {
                    "cpu_percent": "CPU Usage",
                    "ram_percent": "Memory (RAM) Usage",
                    "disk_percent": "Disk Space Usage",
                    "load_1": "Load Average (1m)"
                }
                name = name_map.get(metric_type, metric_type)
                unit = "%" if "percent" in metric_type else ""
                summary.append(f"• *{name}*: Rata-rata `{avg_val:.1f}{unit}`, Puncak `{max_val:.1f}{unit}`")
                
            return "\n".join(summary)
        except Exception as e:
            logger.warning(f"Failed to fetch historical trends: {e}")
            return f"Error mengambil data tren: {e}"

    async def get_disk_report(self) -> str:
        """Laporan penggunaan disk ramah-pemula (untuk /ai cek disk)."""
        r = await self.executor.run(
            "df -h / /var /home 2>/dev/null", module="monitor", check=False,
        )
        m = await self.collect_metrics()
        return (
            f"💽 *Penggunaan Disk*\n"
            f"{self._progress_bar(m['disk_percent'])} `{m['disk_percent']}%` "
            f"(`{m['disk_used_gb']}/{m['disk_total_gb']} GB`)\n\n"
            f"```\n{r['stdout'][:2000]}\n```"
        )

    async def get_top_processes(self) -> str:
        """Top 8 proses berdasarkan CPU & RAM."""
        r = await self.executor.run(
            "ps aux --sort=-%cpu | head -9 | awk '{print $11, $3\"%cpu\", $4\"%mem\"}'",
            module="monitor", check=False,
        )
        return f"🔝 *Top Proses*\n```\n{r['stdout'][:2000]}\n```"

    async def get_connections(self) -> str:
        """Ringkasan koneksi jaringan aktif."""
        r = await self.executor.run(
            "ss -tunp 2>/dev/null | head -20", module="monitor", check=False,
        )
        return f"🌐 *Koneksi Aktif*\n```\n{r['stdout'][:2500]}\n```"

    async def get_state_context(self) -> str:
        """Ringkas state server untuk konteks AI (di-cache 60 detik)."""
        now = time.time()
        if self._state_cache and now - self._state_cache_ts < 60:
            return self._state_cache

        async def installed(pkg):
            r = await self.executor.run(
                f"command -v {pkg} >/dev/null && echo yes || echo no",
                module="monitor", check=False,
            )
            return r["stdout"].strip() == "yes"

        nginx = await installed("nginx")
        mysql = await installed("mysql")
        php = await installed("php")
        lemp = "TERPASANG" if (nginx and mysql and php) else "BELUM terpasang"

        # Daftar site dari DB
        sites = []
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute(
                "SELECT domain, ssl_enabled FROM sites WHERE status='active'"
            )
            sites = cur.fetchall()
            conn.close()
        except Exception:
            pass
        site_str = (
            ", ".join(f"{d}{'(SSL)' if s else ''}" for d, s in sites)
            or "belum ada"
        )

        ctx = (
            f"LEMP stack: {lemp} (nginx={nginx}, mysql={mysql}, php={php}). "
            f"Site terkelola: {site_str}."
        )
        self._state_cache = ctx
        self._state_cache_ts = now
        return ctx
