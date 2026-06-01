"""
PeFi — Pre-Emptive Firewall Agent.

Mengumpulkan data traffic jaringan, mendeteksi anomali secara proaktif,
dan memblokir ancaman sebelum serangan berhasil — berbasis analisis AI.

Sprint 1: Collector + Aggregation + DB + Management API stubs.
"""

import asyncio
import ipaddress
import json
import logging
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger("syamadmin.pefi")


class PreEmptiveFirewall:
    """PeFi — Pre-Emptive Firewall Agent."""

    # Jaringan lokal yang selalu aman — tidak pernah diblokir
    _ALWAYS_TRUSTED_CIDRS = [
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
    ]

    def __init__(self, executor, firewall, brain, notifier,
                 db_path: str, config: dict = None):
        self.executor = executor
        self.firewall = firewall
        self.brain = brain
        self.notifier = notifier
        self.db_path = db_path
        self.config = config or {}
        self._running = False
        self._whitelist_cache: set[str] = set()
        self._trusted_nets = self._build_trusted_nets()
        self.interval = int(self.config.get("PEFI_INTERVAL", 60))
        self.enabled = self.config.get("PEFI_ENABLED", "true").lower() == "true"
        self._ensure_db()
        self._load_whitelist_cache()

    # ------------------------------------------------------------------
    # INISIALISASI
    # ------------------------------------------------------------------

    def _build_trusted_nets(self) -> list:
        extra = self.config.get("PEFI_TRUSTED_NETWORKS", "")
        cidrs = self._ALWAYS_TRUSTED_CIDRS + [s.strip() for s in extra.split(",") if s.strip()]
        nets = []
        for cidr in cidrs:
            try:
                nets.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                logger.warning(f"PeFi: CIDR tidak valid diabaikan: {cidr}")
        return nets

    def _is_trusted(self, ip: str) -> bool:
        if ip in self._whitelist_cache:
            return True
        try:
            addr = ipaddress.ip_address(ip)
            return any(addr in net for net in self._trusted_nets)
        except ValueError:
            return False

    def _ensure_db(self):
        """Buat tabel PeFi di SQLite secara idempoten."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pefi_ip_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ip TEXT NOT NULL,
                    conn_count INTEGER DEFAULT 0,
                    conn_syn INTEGER DEFAULT 0,
                    ports_targeted TEXT DEFAULT '[]',
                    port_count INTEGER DEFAULT 0,
                    ssh_fail_count INTEGER DEFAULT 0,
                    http_req_count INTEGER DEFAULT 0,
                    http_error_count INTEGER DEFAULT 0,
                    flags TEXT DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_pefi_stats_ip
                    ON pefi_ip_stats(ip);
                CREATE INDEX IF NOT EXISTS idx_pefi_stats_ts
                    ON pefi_ip_stats(timestamp);

                CREATE TABLE IF NOT EXISTS pefi_baseline (
                    port INTEGER NOT NULL,
                    hour_of_day INTEGER NOT NULL,
                    avg_conn_per_min REAL DEFAULT 0,
                    stddev_conn REAL DEFAULT 0,
                    avg_unique_ips INTEGER DEFAULT 0,
                    sample_count INTEGER DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (port, hour_of_day)
                );

                CREATE TABLE IF NOT EXISTS pefi_threats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ip TEXT NOT NULL,
                    threat_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    confidence REAL DEFAULT 0,
                    ai_verdict TEXT,
                    ai_reason TEXT,
                    action_taken TEXT DEFAULT 'pending',
                    resolved_at DATETIME,
                    false_positive INTEGER DEFAULT 0,
                    details TEXT DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_pefi_threats_ip
                    ON pefi_threats(ip);

                CREATE TABLE IF NOT EXISTS pefi_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ip TEXT NOT NULL UNIQUE,
                    rule_type TEXT NOT NULL,
                    duration_hours INTEGER,
                    expires_at DATETIME,
                    reason TEXT,
                    threat_id INTEGER,
                    active INTEGER DEFAULT 1,
                    FOREIGN KEY (threat_id) REFERENCES pefi_threats(id)
                );

                CREATE TABLE IF NOT EXISTS pefi_whitelist (
                    ip TEXT PRIMARY KEY,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT,
                    added_by TEXT DEFAULT 'admin'
                );
            """)
            conn.commit()
            conn.close()
            logger.info("PeFi: tabel DB siap.")
        except Exception as e:
            logger.error(f"PeFi DB init error: {e}")

    def _load_whitelist_cache(self):
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT ip FROM pefi_whitelist").fetchall()
            conn.close()
            self._whitelist_cache = {r[0] for r in rows}
        except Exception:
            self._whitelist_cache = set()

    # ------------------------------------------------------------------
    # LAYER 1: COLLECTORS
    # ------------------------------------------------------------------

    async def _collect_connections(self) -> list[dict]:
        """
        Kumpulkan koneksi TCP aktif via `ss`.
        Return: list per-IP {ip, conn_count, conn_syn, ports, port_count}
        """
        ip_ports: defaultdict[str, set] = defaultdict(set)
        ip_conn: defaultdict[str, int] = defaultdict(int)
        ip_syn: defaultdict[str, int] = defaultdict(int)

        # Koneksi established
        res = await self.executor.run(
            "ss -tn state established 2>/dev/null",
            module="pefi", check=False,
        )
        for line in res.get("stdout", "").splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            ip = self._parse_ip_from_peer(parts[4])
            if ip and not self._is_trusted(ip):
                ip_conn[ip] += 1
                port = self._parse_port_from_addr(parts[3])
                if port:
                    ip_ports[ip].add(port)

        # Half-open SYN (SYN flood indicator)
        res_syn = await self.executor.run(
            "ss -tn state syn-recv 2>/dev/null",
            module="pefi", check=False,
        )
        for line in res_syn.get("stdout", "").splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            ip = self._parse_ip_from_peer(parts[4])
            if ip and not self._is_trusted(ip):
                ip_syn[ip] += 1

        all_ips = set(ip_conn) | set(ip_syn)
        return [
            {
                "ip": ip,
                "conn_count": ip_conn[ip],
                "conn_syn": ip_syn[ip],
                "ports": sorted(ip_ports[ip]),
                "port_count": len(ip_ports[ip]),
            }
            for ip in all_ips
        ]

    async def _collect_auth_failures(self) -> list[dict]:
        """
        Parse SSH failures dari auth.log.
        Return: list per-IP {ip, ssh_fail_count}
        """
        res = await self.executor.run(
            "tail -n 500 /var/log/auth.log 2>/dev/null",
            module="pefi", check=False,
        )
        ip_fails: defaultdict[str, int] = defaultdict(int)
        pattern = re.compile(
            r"(?:Failed password|Invalid user|authentication failure)"
            r".*?from\s+([\d.a-fA-F:]+)\s+port"
        )
        for line in res.get("stdout", "").splitlines():
            m = pattern.search(line)
            if m:
                ip = m.group(1)
                if not self._is_trusted(ip):
                    ip_fails[ip] += 1

        return [{"ip": ip, "ssh_fail_count": n} for ip, n in ip_fails.items()]

    async def _collect_nginx_anomalies(self) -> list[dict]:
        """
        Parse Nginx access.log untuk deteksi request spike dan error rate per IP.
        Return: list per-IP {ip, http_req_count, http_error_count}
        """
        res = await self.executor.run(
            "tail -n 2000 /var/log/nginx/access.log 2>/dev/null",
            module="pefi", check=False,
        )
        ip_reqs: defaultdict[str, int] = defaultdict(int)
        ip_errors: defaultdict[str, int] = defaultdict(int)

        # Nginx combined log format:
        # 1.2.3.4 - - [01/Jun/2026:12:34:56 +0700] "GET / HTTP/1.1" 200 1234
        pattern = re.compile(
            r'^([\d.a-fA-F:]+)\s+\S+\s+\S+\s+\[[^\]]+\]\s+"[^"]*"\s+(\d{3})'
        )
        for line in res.get("stdout", "").splitlines():
            m = pattern.match(line)
            if m:
                ip, status = m.group(1), int(m.group(2))
                if not self._is_trusted(ip):
                    ip_reqs[ip] += 1
                    if status >= 400:
                        ip_errors[ip] += 1

        return [
            {
                "ip": ip,
                "http_req_count": ip_reqs[ip],
                "http_error_count": ip_errors[ip],
            }
            for ip in ip_reqs
        ]

    async def _collect_kernel_stats(self) -> dict:
        """
        Baca /proc/net/sockstat untuk ringkasan socket kernel.
        Hanya tersedia di Linux; return {} di macOS secara graceful.
        """
        stats = {}
        res = await self.executor.run(
            "cat /proc/net/sockstat 2>/dev/null",
            module="pefi", check=False,
        )
        for line in res.get("stdout", "").splitlines():
            parts = line.split()
            if line.startswith("TCP:"):
                try:
                    stats["tcp_inuse"] = int(parts[parts.index("inuse") + 1])
                    stats["tcp_tw"] = int(parts[parts.index("tw") + 1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith("UDP:"):
                try:
                    stats["udp_inuse"] = int(parts[parts.index("inuse") + 1])
                except (ValueError, IndexError):
                    pass
        return stats

    # ------------------------------------------------------------------
    # LAYER 2: AGGREGATION ENGINE
    # ------------------------------------------------------------------

    async def _aggregate(
        self,
        conn_stats: list[dict],
        auth_stats: list[dict],
        nginx_stats: list[dict],
    ) -> list[dict]:
        """
        Gabungkan output semua collector menjadi satu statistik per-IP.
        """
        merged: dict[str, dict] = {}

        def _get(ip: str) -> dict:
            if ip not in merged:
                merged[ip] = {
                    "ip": ip,
                    "conn_count": 0,
                    "conn_syn": 0,
                    "ports_targeted": [],
                    "port_count": 0,
                    "ssh_fail_count": 0,
                    "http_req_count": 0,
                    "http_error_count": 0,
                    "flags": {},
                }
            return merged[ip]

        for s in conn_stats:
            e = _get(s["ip"])
            e["conn_count"] += s.get("conn_count", 0)
            e["conn_syn"] += s.get("conn_syn", 0)
            ports = set(e["ports_targeted"]) | set(s.get("ports", []))
            e["ports_targeted"] = sorted(ports)
            e["port_count"] = len(e["ports_targeted"])

        for s in auth_stats:
            _get(s["ip"])["ssh_fail_count"] += s.get("ssh_fail_count", 0)

        for s in nginx_stats:
            e = _get(s["ip"])
            e["http_req_count"] += s.get("http_req_count", 0)
            e["http_error_count"] += s.get("http_error_count", 0)

        return list(merged.values())

    def _store_ip_stats(self, stats: list[dict]):
        """Simpan snapshot statistik per-IP ke SQLite."""
        if not stats:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            conn.executemany(
                """INSERT INTO pefi_ip_stats
                   (ip, conn_count, conn_syn, ports_targeted, port_count,
                    ssh_fail_count, http_req_count, http_error_count, flags)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        s["ip"],
                        s["conn_count"],
                        s["conn_syn"],
                        json.dumps(s["ports_targeted"]),
                        s["port_count"],
                        s["ssh_fail_count"],
                        s["http_req_count"],
                        s["http_error_count"],
                        json.dumps(s.get("flags", {})),
                    )
                    for s in stats
                ],
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PeFi: gagal simpan stats: {e}")

    def _prune_old_data(self):
        """Hapus data pefi_ip_stats lebih dari 7 hari & nonaktifkan rule expired."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "DELETE FROM pefi_ip_stats WHERE timestamp < datetime('now', '-7 days')"
            )
            conn.execute(
                """UPDATE pefi_rules SET active=0
                   WHERE expires_at IS NOT NULL AND expires_at < datetime('now')"""
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PeFi prune error: {e}")

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    async def _tick(self):
        """Satu siklus: collect → aggregate → store. Anomali detection di Sprint 2."""
        logger.debug("PeFi tick: mengumpulkan data traffic...")

        results = await asyncio.gather(
            self._collect_connections(),
            self._collect_auth_failures(),
            self._collect_nginx_anomalies(),
            self._collect_kernel_stats(),
            return_exceptions=True,
        )

        conn_stats  = results[0] if isinstance(results[0], list) else []
        auth_stats  = results[1] if isinstance(results[1], list) else []
        nginx_stats = results[2] if isinstance(results[2], list) else []
        # results[3] = kernel_stats dict, dipakai Sprint 2

        for i, r in enumerate(results[:3]):
            if isinstance(r, Exception):
                logger.warning(f"PeFi collector[{i}] error: {r}")

        aggregated = await self._aggregate(conn_stats, auth_stats, nginx_stats)
        self._store_ip_stats(aggregated)
        self._prune_old_data()

        if aggregated:
            logger.info(
                f"PeFi tick selesai: {len(aggregated)} IP dipantau "
                f"(conn={sum(s['conn_count'] for s in aggregated)}, "
                f"ssh_fail={sum(s['ssh_fail_count'] for s in aggregated)}, "
                f"http_err={sum(s['http_error_count'] for s in aggregated)})"
            )

    async def run_loop(self):
        """Background async task — parallel dengan bot & monitor."""
        if not self.enabled:
            logger.info("PeFi dinonaktifkan (PEFI_ENABLED=false).")
            return
        self._running = True
        logger.info(f"🛡️ PeFi started (interval={self.interval}s)")
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"PeFi loop error: {e}", exc_info=True)
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # MANAGEMENT API  (dipakai Telegram commands — Sprint 4)
    # ------------------------------------------------------------------

    async def get_status(self) -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            threats_24h = conn.execute(
                "SELECT COUNT(*) FROM pefi_threats WHERE detected_at > datetime('now','-24 hours')"
            ).fetchone()[0]
            active_rules = conn.execute(
                "SELECT COUNT(*) FROM pefi_rules WHERE active=1"
            ).fetchone()[0]
            whitelisted = conn.execute(
                "SELECT COUNT(*) FROM pefi_whitelist"
            ).fetchone()[0]
            ip_1h, last_scan = conn.execute(
                "SELECT COUNT(DISTINCT ip), MAX(timestamp) FROM pefi_ip_stats "
                "WHERE timestamp > datetime('now','-1 hour')"
            ).fetchone()
            conn.close()

            status_icon = "🟢" if (self._running and self.enabled) else "🔴"
            status_text = "Aktif" if (self._running and self.enabled) else "Nonaktif"
            return (
                f"🛡️ *PeFi — Pre-Emptive Firewall*\n\n"
                f"• Status       : {status_icon} {status_text}\n"
                f"• Interval     : `{self.interval}s`\n"
                f"• IP dipantau  : `{ip_1h or 0}` (1 jam terakhir)\n"
                f"• Ancaman 24j  : `{threats_24h}`\n"
                f"• Aturan aktif : `{active_rules}`\n"
                f"• Whitelist    : `{whitelisted}` IP\n"
                f"• Scan terakhir: `{last_scan or 'belum ada data'}`\n\n"
                f"_`/pefi threats` · `/pefi rules` · `/pefi scan`_"
            )
        except Exception as e:
            return f"❌ Gagal ambil status PeFi: {e}"

    async def get_active_threats(self) -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                """SELECT ip, threat_type, severity, action_taken, detected_at
                   FROM pefi_threats
                   WHERE detected_at > datetime('now','-24 hours')
                   ORDER BY detected_at DESC LIMIT 15"""
            ).fetchall()
            conn.close()

            if not rows:
                return "✅ Tidak ada ancaman terdeteksi dalam 24 jam terakhir."
            icons = {"CRITICAL": "💀", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}
            lines = ["⚠️ *Ancaman Terdeteksi (24 jam terakhir)*\n"]
            for ip, ttype, sev, action, ts in rows:
                lines.append(
                    f"{icons.get(sev,'⚪')} `{ip}` — {ttype} [{sev}]\n"
                    f"   Aksi: `{action}` | {ts[:16]}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Gagal ambil data ancaman: {e}"

    async def get_active_rules(self) -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                """SELECT ip, rule_type, reason, created_at, expires_at
                   FROM pefi_rules WHERE active=1
                   ORDER BY created_at DESC LIMIT 20"""
            ).fetchall()
            conn.close()

            if not rows:
                return "✅ Tidak ada aturan PeFi aktif saat ini."
            lines = ["🔒 *Aturan Aktif PeFi*\n"]
            for ip, rtype, reason, created, expires in rows:
                exp = f"hingga `{expires[:16]}`" if expires else "permanen"
                lines.append(f"• `{ip}` — {rtype.upper()} ({exp})\n  _{reason}_")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Gagal ambil aturan PeFi: {e}"

    async def whitelist_ip(self, ip: str, reason: str = "manual oleh admin") -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO pefi_whitelist (ip, reason, added_by) VALUES (?,?,?)",
                (ip, reason, "admin"),
            )
            conn.commit()
            conn.close()
            self._whitelist_cache.add(ip)
            return (
                f"✅ `{ip}` ditambahkan ke whitelist PeFi.\n"
                f"IP ini tidak akan diproses oleh sistem deteksi ancaman."
            )
        except Exception as e:
            return f"❌ Gagal whitelist IP: {e}"

    async def remove_rule(self, ip: str) -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            affected = conn.execute(
                "SELECT id FROM pefi_rules WHERE ip=? AND active=1", (ip,)
            ).fetchall()
            conn.execute(
                "UPDATE pefi_rules SET active=0 WHERE ip=? AND active=1", (ip,)
            )
            conn.commit()
            conn.close()
            if not affected:
                return f"ℹ️ Tidak ada aturan aktif PeFi untuk `{ip}`."
            await self.firewall.allow_ip(ip, comment="PeFi unblock by admin")
            return f"✅ Blokir PeFi untuk `{ip}` dihapus.\nIP sekarang dapat mengakses server kembali."
        except Exception as e:
            return f"❌ Gagal hapus aturan: {e}"

    async def scan_now(self) -> str:
        try:
            await self._tick()
            return "✅ PeFi scan manual selesai. Data traffic terbaru tersimpan di database."
        except Exception as e:
            return f"❌ Scan manual gagal: {e}"

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ip_from_peer(peer: str) -> Optional[str]:
        """Ekstrak IP dari peer address ss: '1.2.3.4:54321' atau '[::1]:54321'."""
        if not peer or peer in ("*", "-"):
            return None
        if peer.startswith("["):
            m = re.match(r"\[([^\]]+)\]", peer)
            return m.group(1) if m else None
        if ":" in peer:
            return peer.rsplit(":", 1)[0] or None
        return None

    @staticmethod
    def _parse_port_from_addr(addr: str) -> Optional[int]:
        """Ekstrak port dari local address ss: '0.0.0.0:80' → 80."""
        if ":" in addr:
            try:
                return int(addr.rsplit(":", 1)[1])
            except ValueError:
                pass
        return None
