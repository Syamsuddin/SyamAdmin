"""
PeFi — Pre-Emptive Firewall Agent.

Mengumpulkan data traffic jaringan, mendeteksi anomali secara proaktif,
dan memblokir ancaman sebelum serangan berhasil — berbasis analisis AI.

Sprint 1: Collector + Aggregation + DB + Management API stubs.
Sprint 2: Baseline Engine + Anomaly Detector (6 rule-based checks).
"""

import asyncio
import ipaddress
import json
import logging
import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("syamadmin.pefi")

# Alpha untuk Exponential Moving Average baseline — makin kecil makin stabil
_EMA_ALPHA = 0.15

# Minimum sigma (standar deviasi) untuk hindari false positive saat traffic sangat tenang
_MIN_STDDEV = 2.0


@dataclass
class ThreatEvent:
    """Satu kejadian anomali yang terdeteksi pada satu IP."""
    ip: str
    threat_type: str    # PORT_SCAN | SYN_FLOOD | BRUTE_FORCE | CONN_SPIKE | TRAFFIC_SPIKE | RECON | RECIDIVIST
    severity: str       # LOW | MEDIUM | HIGH | CRITICAL
    details: dict = field(default_factory=dict)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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

        # Threshold anomali — semua overridable via config.env
        self._thr_conn       = int(self.config.get("PEFI_THRESHOLD_CONN_PER_MIN", 200))
        self._thr_port_scan  = int(self.config.get("PEFI_THRESHOLD_PORT_SCAN", 10))
        self._thr_syn        = int(self.config.get("PEFI_THRESHOLD_SYN", 50))
        self._thr_spike_mult = float(self.config.get("PEFI_THRESHOLD_SPIKE_MULTIPLIER", 3.0))
        self._thr_ssh_fail   = int(self.config.get("PEFI_THRESHOLD_SSH_FAIL", 20))
        self._thr_http_err   = int(self.config.get("PEFI_THRESHOLD_HTTP_ERRORS", 50))
        self._baseline_min   = int(self.config.get("PEFI_BASELINE_MIN_SAMPLES", 10))

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
                    m2_conn REAL DEFAULT 0,
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
            # Sprint 2 migration: tambah m2_conn ke baseline jika belum ada
            cols = {r[1] for r in conn.execute("PRAGMA table_info(pefi_baseline)").fetchall()}
            if "m2_conn" not in cols:
                conn.execute("ALTER TABLE pefi_baseline ADD COLUMN m2_conn REAL DEFAULT 0")
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
    # LAYER 3: BASELINE ENGINE
    # ------------------------------------------------------------------

    def _update_baseline(self, aggregated: list[dict]):
        """
        Perbarui baseline traffic normal per-port per-jam menggunakan
        algoritma Welford's online (incremental mean + variance tanpa
        menyimpan seluruh history).

        Dipanggil setiap tick SEBELUM anomaly detection agar baseline
        tidak tercemar oleh kejadian yang sedang terjadi saat ini.
        """
        if not aggregated:
            return

        hour = datetime.now(timezone.utc).hour
        # Hitung total koneksi per-port dari semua IP di interval ini
        port_conn: defaultdict[int, int] = defaultdict(int)
        port_ips: defaultdict[int, set] = defaultdict(set)

        for s in aggregated:
            for port in s.get("ports_targeted", []):
                port_conn[port] += s["conn_count"]
                port_ips[port].add(s["ip"])

        if not port_conn:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            for port, total_conn in port_conn.items():
                row = conn.execute(
                    "SELECT avg_conn_per_min, m2_conn, stddev_conn, avg_unique_ips, sample_count "
                    "FROM pefi_baseline WHERE port=? AND hour_of_day=?",
                    (port, hour),
                ).fetchone()

                if row is None:
                    # Sampel pertama untuk port+jam ini
                    conn.execute(
                        """INSERT INTO pefi_baseline
                           (port, hour_of_day, avg_conn_per_min, m2_conn, stddev_conn,
                            avg_unique_ips, sample_count)
                           VALUES (?,?,?,0,0,?,1)""",
                        (port, hour, float(total_conn), len(port_ips[port])),
                    )
                else:
                    old_avg, old_m2, _, old_unique, n = row
                    n_new = n + 1
                    # Welford's online algorithm
                    delta = total_conn - old_avg
                    new_avg = old_avg + delta / n_new
                    delta2 = total_conn - new_avg
                    new_m2 = old_m2 + delta * delta2
                    new_stddev = math.sqrt(new_m2 / n_new) if n_new >= 2 else 0.0
                    # EMA untuk unique IPs (tidak perlu presisi tinggi)
                    new_unique = int((1 - _EMA_ALPHA) * old_unique + _EMA_ALPHA * len(port_ips[port]))
                    conn.execute(
                        """UPDATE pefi_baseline
                           SET avg_conn_per_min=?, m2_conn=?, stddev_conn=?,
                               avg_unique_ips=?, sample_count=?, updated_at=CURRENT_TIMESTAMP
                           WHERE port=? AND hour_of_day=?""",
                        (new_avg, new_m2, new_stddev, new_unique, n_new, port, hour),
                    )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PeFi baseline update error: {e}")

    def _load_baseline(self) -> dict[tuple, dict]:
        """Muat baseline dari DB untuk jam saat ini → dipakai anomaly detector."""
        hour = datetime.now(timezone.utc).hour
        result: dict[tuple, dict] = {}
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT port, avg_conn_per_min, stddev_conn, sample_count "
                "FROM pefi_baseline WHERE hour_of_day=?",
                (hour,),
            ).fetchall()
            conn.close()
            for port, avg, stddev, n in rows:
                result[(port, hour)] = {
                    "avg": avg,
                    "stddev": max(stddev, _MIN_STDDEV),
                    "sample_count": n,
                }
        except Exception as e:
            logger.warning(f"PeFi load baseline error: {e}")
        return result

    # ------------------------------------------------------------------
    # LAYER 4: ANOMALY DETECTOR (rule-based, tanpa AI)
    # ------------------------------------------------------------------

    def _detect_anomalies(
        self, aggregated: list[dict], baseline: dict
    ) -> list[ThreatEvent]:
        """
        Jalankan 6 + 1 rule-based checks terhadap data aggregated.
        Return list ThreatEvent — kosong jika tidak ada anomali.

        Checks:
          1. PORT_SCAN    — terlalu banyak port unik dari satu IP
          2. SYN_FLOOD    — terlalu banyak half-open SYN dari satu IP
          3. BRUTE_FORCE  — terlalu banyak SSH login failure dari satu IP
          4. CONN_SPIKE   — koneksi per-interval dari satu IP melampaui threshold absolut
          5. TRAFFIC_SPIKE— koneksi ke port tertentu jauh di atas baseline historis
          6. RECON        — terlalu banyak HTTP 4xx error (penjelajahan celah)
          7. RECIDIVIST   — IP yang pernah diblokir PeFi muncul lagi
        """
        threats: list[ThreatEvent] = []
        hour = datetime.now(timezone.utc).hour

        # Per-port aggregate untuk TRAFFIC_SPIKE check
        port_total: defaultdict[int, int] = defaultdict(int)
        for s in aggregated:
            for port in s.get("ports_targeted", []):
                port_total[port] += s["conn_count"]

        recidivists = self._get_recidivist_ips()

        for s in aggregated:
            ip = s["ip"]

            # 1. PORT_SCAN
            if s["port_count"] >= self._thr_port_scan:
                severity = "CRITICAL" if s["port_count"] >= self._thr_port_scan * 3 else "HIGH"
                threats.append(ThreatEvent(
                    ip=ip, threat_type="PORT_SCAN", severity=severity,
                    details={
                        "port_count": s["port_count"],
                        "ports_sample": s["ports_targeted"][:10],
                        "threshold": self._thr_port_scan,
                    },
                ))

            # 2. SYN_FLOOD
            if s["conn_syn"] >= self._thr_syn:
                severity = "CRITICAL" if s["conn_syn"] >= self._thr_syn * 2 else "HIGH"
                threats.append(ThreatEvent(
                    ip=ip, threat_type="SYN_FLOOD", severity=severity,
                    details={
                        "syn_count": s["conn_syn"],
                        "threshold": self._thr_syn,
                    },
                ))

            # 3. BRUTE_FORCE (SSH)
            if s["ssh_fail_count"] >= self._thr_ssh_fail:
                severity = "HIGH" if s["ssh_fail_count"] >= self._thr_ssh_fail * 2 else "MEDIUM"
                threats.append(ThreatEvent(
                    ip=ip, threat_type="BRUTE_FORCE", severity=severity,
                    details={
                        "ssh_fail_count": s["ssh_fail_count"],
                        "threshold": self._thr_ssh_fail,
                    },
                ))

            # 4. CONN_SPIKE (absolute)
            if s["conn_count"] >= self._thr_conn:
                severity = "HIGH" if s["conn_count"] >= self._thr_conn * 2 else "MEDIUM"
                threats.append(ThreatEvent(
                    ip=ip, threat_type="CONN_SPIKE", severity=severity,
                    details={
                        "conn_count": s["conn_count"],
                        "threshold": self._thr_conn,
                    },
                ))

            # 6. RECON (HTTP error flood)
            if s["http_error_count"] >= self._thr_http_err:
                severity = "HIGH" if s["http_error_count"] >= self._thr_http_err * 3 else "MEDIUM"
                threats.append(ThreatEvent(
                    ip=ip, threat_type="RECON", severity=severity,
                    details={
                        "http_error_count": s["http_error_count"],
                        "http_req_count": s["http_req_count"],
                        "threshold": self._thr_http_err,
                    },
                ))

            # 7. RECIDIVIST
            if ip in recidivists and s["conn_count"] > 0:
                threats.append(ThreatEvent(
                    ip=ip, threat_type="RECIDIVIST", severity="HIGH",
                    details={
                        "previous_blocks": recidivists[ip],
                        "current_conn": s["conn_count"],
                    },
                ))

        # 5. TRAFFIC_SPIKE (per-port, baseline comparison)
        for port, total in port_total.items():
            key = (port, hour)
            bl = baseline.get(key)
            if not bl or bl["sample_count"] < self._baseline_min:
                continue  # Baseline belum cukup sampel
            threshold_val = bl["avg"] + self._thr_spike_mult * bl["stddev"]
            if total > threshold_val and total > bl["avg"] * self._thr_spike_mult:
                # Cari IP penyumbang terbesar sebagai representasi
                top_ip = max(
                    (s for s in aggregated if port in s.get("ports_targeted", [])),
                    key=lambda x: x["conn_count"],
                    default=None,
                )
                if top_ip:
                    threats.append(ThreatEvent(
                        ip=top_ip["ip"],
                        threat_type="TRAFFIC_SPIKE",
                        severity="MEDIUM",
                        details={
                            "port": port,
                            "total_conn": total,
                            "baseline_avg": round(bl["avg"], 1),
                            "baseline_stddev": round(bl["stddev"], 1),
                            "threshold": round(threshold_val, 1),
                            "multiplier": round(total / max(bl["avg"], 1), 1),
                        },
                    ))

        return threats

    def _get_recidivist_ips(self) -> dict[str, int]:
        """Return dict {ip: jumlah_block_sebelumnya} untuk IP yang pernah diblokir PeFi."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                """SELECT ip, COUNT(*) as cnt FROM pefi_rules
                   WHERE rule_type='block' GROUP BY ip HAVING cnt > 0"""
            ).fetchall()
            conn.close()
            return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    def _save_threats(self, threats: list[ThreatEvent]):
        """
        Simpan ThreatEvent ke DB dengan deduplication:
        IP + threat_type yang sama dalam 60 menit terakhir diabaikan
        (kecuali severity meningkat).
        """
        if not threats:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            saved = 0
            for t in threats:
                # Cek duplikat dalam 60 menit
                existing = conn.execute(
                    """SELECT id, severity FROM pefi_threats
                       WHERE ip=? AND threat_type=?
                         AND detected_at > datetime('now', '-60 minutes')
                         AND action_taken != 'resolved'
                       ORDER BY detected_at DESC LIMIT 1""",
                    (t.ip, t.threat_type),
                ).fetchone()

                severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
                if existing:
                    old_rank = severity_rank.get(existing[1], 0)
                    new_rank = severity_rank.get(t.severity, 0)
                    if new_rank <= old_rank:
                        continue  # Sudah dilaporkan, severity tidak meningkat

                conn.execute(
                    """INSERT INTO pefi_threats
                       (ip, threat_type, severity, action_taken, details)
                       VALUES (?,?,?,'pending',?)""",
                    (t.ip, t.threat_type, t.severity, json.dumps(t.details)),
                )
                saved += 1

            conn.commit()
            conn.close()
            if saved:
                logger.info(f"PeFi: {saved} ancaman baru disimpan ke DB.")
        except Exception as e:
            logger.warning(f"PeFi save threats error: {e}")

    def _get_pending_threats(self) -> list[dict]:
        """Ambil ancaman dengan status 'pending' untuk diproses (Sprint 3: AI analysis)."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                """SELECT id, ip, threat_type, severity, details
                   FROM pefi_threats
                   WHERE action_taken='pending'
                     AND detected_at > datetime('now', '-30 minutes')
                   ORDER BY
                     CASE severity
                       WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                       WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                     detected_at DESC
                   LIMIT 20""",
            ).fetchall()
            conn.close()
            return [
                {
                    "id": r[0], "ip": r[1], "threat_type": r[2],
                    "severity": r[3], "details": json.loads(r[4] or "{}"),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"PeFi get pending threats error: {e}")
            return []

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    async def _tick(self):
        """Satu siklus: collect → aggregate → baseline → detect → save → notify."""
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

        for i, label in enumerate(["connections", "auth", "nginx"]):
            if isinstance(results[i], Exception):
                logger.warning(f"PeFi collector[{label}] error: {results[i]}")

        aggregated = await self._aggregate(conn_stats, auth_stats, nginx_stats)
        self._store_ip_stats(aggregated)

        # Sprint 2: Baseline update SEBELUM detect (agar data saat ini
        # tidak langsung mempengaruhi threshold yang akan memeriksa dirinya sendiri)
        baseline = self._load_baseline()
        self._update_baseline(aggregated)

        # Deteksi anomali
        threats = self._detect_anomalies(aggregated, baseline)
        self._save_threats(threats)

        # Notifikasi ke Telegram untuk ancaman HIGH/CRITICAL (Sprint 4: + AI analysis)
        critical = [t for t in threats if t.severity in ("HIGH", "CRITICAL")]
        if critical:
            await self._notify_threats(critical)

        self._prune_old_data()

        logger.info(
            f"PeFi tick: {len(aggregated)} IP, "
            f"{len(threats)} ancaman baru "
            f"({len(critical)} HIGH/CRITICAL)"
        )

    async def _notify_threats(self, threats: list[ThreatEvent]):
        """Kirim ringkasan ancaman HIGH/CRITICAL ke Telegram admin."""
        if not threats:
            return
        icons = {"CRITICAL": "💀", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}
        lines = ["🛡️ *PeFi — Ancaman Terdeteksi*\n"]
        for t in threats[:5]:  # maks 5 per notifikasi agar tidak spam
            icon = icons.get(t.severity, "⚪")
            detail_str = ""
            if t.threat_type == "PORT_SCAN":
                detail_str = f"scan {t.details.get('port_count')} port"
            elif t.threat_type == "SYN_FLOOD":
                detail_str = f"{t.details.get('syn_count')} SYN half-open"
            elif t.threat_type == "BRUTE_FORCE":
                detail_str = f"{t.details.get('ssh_fail_count')} SSH failures"
            elif t.threat_type == "CONN_SPIKE":
                detail_str = f"{t.details.get('conn_count')} koneksi (threshold: {t.details.get('threshold')})"
            elif t.threat_type == "TRAFFIC_SPIKE":
                detail_str = f"port {t.details.get('port')}: {t.details.get('multiplier')}x di atas baseline"
            elif t.threat_type == "RECON":
                detail_str = f"{t.details.get('http_error_count')} HTTP errors"
            elif t.threat_type == "RECIDIVIST":
                detail_str = f"pernah diblokir {t.details.get('previous_blocks')}x"
            lines.append(
                f"{icon} `{t.ip}` — *{t.threat_type}* [{t.severity}]\n"
                f"   {detail_str}"
            )
        if len(threats) > 5:
            lines.append(f"\n_...dan {len(threats) - 5} ancaman lainnya._")
        lines.append("\n_Ketik `/pefi threats` untuk detail lengkap._")
        try:
            await self.notifier.send("\n".join(lines))
        except Exception as e:
            logger.warning(f"PeFi notify error: {e}")

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
