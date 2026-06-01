# PeFi — Pre-Emptive Firewall Agent
## Desain Arsitektur Lengkap untuk SyamAdmin

> Branch: `feature/pre-emptive-firewall-agen`
> Status: Design Document v1.0

---

## 1. Latar Belakang & Masalah

Firewall SyamAdmin saat ini bersifat **reaktif**:

```
Serangan terjadi → Log tertulis → Fail2Ban/UFW bereaksi → IP diblokir
```

Masalahnya:
- Serangan pertama selalu lolos sebelum diblokir
- Fail2Ban hanya lihat auth.log (SSH) — tidak tahu pola traffic di port lain
- Tidak ada memory lintas sesi: IP yang pernah nyerang bisa bebas lagi setelah ban expire
- Tidak bisa bedakan traffic normal vs anomali berdasarkan konteks historis

**PeFi** membalik alurnya menjadi **pre-emptive**:

```
Kumpulkan data traffic → Bangun baseline normal → Deteksi anomali →
AI analisis konteks → Blokir SEBELUM serangan berhasil merusak
```

---

## 2. Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────────┐
│                     LAYER 1: COLLECTOR                          │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  ss/     │  │ iptables │  │ auth.log │  │nginx/apache  │   │
│  │ netstat  │  │   LOG    │  │ fail2ban │  │  access.log  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
│       └─────────────┴─────────────┴────────────────┘           │
│                             ↓                                   │
│                    NetworkCollector                             │
│            (async, tiap 60 detik + event-driven)               │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   LAYER 2: AGGREGATION ENGINE                   │
│                                                                 │
│   Per-IP Stats       Per-Port Stats      Time-Series            │
│   ┌──────────┐       ┌──────────┐       ┌──────────┐           │
│   │koneksi/mn│       │req/menit │       │baseline  │           │
│   │fail count│       │error rate│       │7-hari    │           │
│   │geo info  │       │syn flood │       │rolling   │           │
│   │port scan │       │half-open │       │avg/stddev│           │
│   └──────────┘       └──────────┘       └──────────┘           │
│                             ↓                                   │
│                    AggregationEngine                            │
│              (hitung delta vs baseline, flag anomali)           │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  LAYER 3: ANOMALY DETECTOR                      │
│                                                                 │
│   Rule-Based (cepat, tanpa AI):                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ • >200 koneksi/menit dari 1 IP → FLAG: HIGH             │   │
│   │ • >10 port berbeda dalam 60 detik → FLAG: PORT_SCAN     │   │
│   │ • >50 koneksi HALF-OPEN (SYN) → FLAG: SYN_FLOOD        │   │
│   │ • IP ada di local threat DB → FLAG: KNOWN_BAD           │   │
│   │ • Traffic 3x di atas baseline → FLAG: SPIKE             │   │
│   │ • Koneksi ke port tertutup → FLAG: RECON                │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   Hasilnya: daftar ThreatEvent dengan severity (LOW/MED/HIGH)  │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓ (hanya jika ada anomali)
┌─────────────────────────────────────────────────────────────────┐
│                  LAYER 4: AI ANALYSIS ENGINE                    │
│                                                                 │
│   Input ke Claude (ringkasan, bukan paket mentah):             │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  - ThreatEvent list + severity                          │   │
│   │  - Konteks server (layanan aktif, port listen)          │   │
│   │  - Riwayat IP (pernah diblokir? kapan? kenapa?)         │   │
│   │  - Baseline traffic normal server ini                   │   │
│   │  - Waktu (jam sibuk vs malam — pola berbeda)            │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   Output dari Claude (structured tool-use):                    │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  - verdict: BLOCK / MONITOR / WHITELIST / IGNORE        │   │
│   │  - confidence: 0.0-1.0                                  │   │
│   │  - reason: penjelasan dalam bahasa Indonesia            │   │
│   │  - action: {type, target, duration, rule}               │   │
│   │  - risk_if_wrong: dampak jika keputusan salah           │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  LAYER 5: DECISION ENGINE                       │
│                                                                 │
│   TIER 1 — AUTO-BLOCK (tanpa konfirmasi):                       │
│     confidence ≥ 0.95 DAN severity = HIGH DAN IP bukan          │
│     whitelist → langsung block, notif Telegram                 │
│                                                                 │
│   TIER 2 — KONFIRMASI OTP (default untuk HIGH):                 │
│     confidence 0.75-0.94 ATAU severity = MED → kirim            │
│     notifikasi ke Telegram + OTP, tunggu konfirmasi admin      │
│                                                                 │
│   TIER 3 — MONITOR SAJA:                                        │
│     confidence < 0.75 ATAU severity = LOW → catat di DB,       │
│     pantau terus, tidak ada aksi langsung                      │
│                                                                 │
│   TIER 0 — BYPASS (whitelist):                                  │
│     IP di whitelist → abaikan semua flag, tidak diproses       │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   LAYER 6: ACTION ENGINE                        │
│                                                                 │
│   ┌────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│   │  UFW deny_ip   │  │  iptables rate  │  │  Threat DB     │  │
│   │  (permanen     │  │  limit rule     │  │  update        │  │
│   │  atau TTL)     │  │  (throttle)     │  │  (lokal)       │  │
│   └────────────────┘  └─────────────────┘  └────────────────┘  │
│                                                                 │
│   Setiap aksi → audit_log SQLite + Telegram notifikasi         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Sumber Data & Pengumpulan

### 3.1 ss / netstat (koneksi aktif)
```bash
ss -tnp state established   # koneksi TCP aktif
ss -tnp state syn-recv      # half-open (SYN flood indicator)
ss -u -a                    # UDP connections
```
Dikumpulkan: **setiap 60 detik**
Data: source IP, destination port, state, PID

### 3.2 iptables LOG (metadata paket)
Tambahkan rule logging di INPUT chain:
```bash
# Tambahkan saat PeFi init (sebelum DROP rules):
iptables -I INPUT -m limit --limit 10/minute -j LOG \
  --log-prefix "[PEFI] " --log-level 4
```
Log masuk ke `/var/log/kern.log` atau `dmesg`.
Dikumpulkan: **tail -f** (event-driven, bukan polling)
Data: source IP, destination port, protocol, flags TCP

### 3.3 auth.log
```bash
tail -n 500 /var/log/auth.log
```
Dikumpulkan: **setiap 60 detik**
Data: SSH login attempt, failed password, invalid user, accepted

### 3.4 Nginx access.log
```bash
tail -n 1000 /var/log/nginx/access.log
```
Dikumpulkan: **setiap 60 detik**
Data: IP, status code (400/404/429), request rate, user-agent anomali

### 3.5 /proc/net (statistik kernel)
```bash
cat /proc/net/nstat          # packet counters
cat /proc/net/dev            # bytes per interface
cat /proc/net/sockstat       # socket summary
```
Dikumpulkan: **setiap 30 detik** (ringan, baca file saja)

---

## 4. Database Schema (SQLite Extension)

Ditambahkan ke `/var/lib/syamadmin/syamadmin.db`:

```sql
-- Statistik traffic per IP per interval
CREATE TABLE IF NOT EXISTS pefi_ip_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip TEXT NOT NULL,
    country_code TEXT,          -- 'ID', 'CN', 'RU', dll
    conn_count INTEGER,         -- total koneksi dalam interval
    conn_failed INTEGER,        -- koneksi gagal / rejected
    ports_targeted TEXT,        -- JSON array port yang diakses
    port_count INTEGER,         -- jumlah port unik
    syn_count INTEGER,          -- half-open SYN
    bytes_in INTEGER,
    bytes_out INTEGER,
    flags TEXT                  -- JSON: {ssh_fail, port_scan, syn_flood, ...}
);

-- Baseline traffic normal (diupdate rolling 7 hari)
CREATE TABLE IF NOT EXISTS pefi_baseline (
    port INTEGER NOT NULL,
    hour_of_day INTEGER NOT NULL,   -- 0-23
    avg_conn_per_min REAL,
    stddev_conn REAL,
    avg_unique_ips INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (port, hour_of_day)
);

-- Riwayat ancaman terdeteksi
CREATE TABLE IF NOT EXISTS pefi_threats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip TEXT NOT NULL,
    threat_type TEXT,           -- PORT_SCAN, SYN_FLOOD, BRUTE_FORCE, SPIKE, RECON
    severity TEXT,              -- LOW, MEDIUM, HIGH, CRITICAL
    confidence REAL,            -- 0.0-1.0 dari AI
    ai_verdict TEXT,            -- BLOCK, MONITOR, WHITELIST, IGNORE
    ai_reason TEXT,
    action_taken TEXT,          -- blocked, throttled, monitored, ignored
    resolved_at DATETIME,
    false_positive INTEGER DEFAULT 0
);

-- Aturan aktif yang dibuat PeFi
CREATE TABLE IF NOT EXISTS pefi_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip TEXT NOT NULL,
    rule_type TEXT,             -- block, throttle, monitor
    duration_hours INTEGER,     -- NULL = permanen
    expires_at DATETIME,
    ufw_rule_number INTEGER,    -- untuk cleanup otomatis
    reason TEXT,
    active INTEGER DEFAULT 1
);

-- Whitelist IP yang tidak boleh disentuh PeFi
CREATE TABLE IF NOT EXISTS pefi_whitelist (
    ip TEXT PRIMARY KEY,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    added_by TEXT               -- 'admin' atau 'system'
);
```

---

## 5. Modul Baru: `modules/pefi.py`

### Class Utama

```python
class PreEmptiveFirewall:
    """
    PeFi — Pre-Emptive Firewall Agent.
    Menganalisis pola traffic jaringan secara proaktif menggunakan AI
    untuk mendeteksi dan memblokir ancaman sebelum berhasil menyerang.
    """

    def __init__(self, executor, firewall, brain, notifier, db_path, config):
        self.executor = executor      # CommandExecutor (jalankan shell)
        self.firewall = firewall      # FirewallManager (UFW deny_ip)
        self.brain = brain            # AIBrain (analisis Claude)
        self.notifier = notifier      # Notifier (alert Telegram)
        self.db_path = db_path
        self.config = config
        self._whitelist_cache = set()
        self._running = False

    # --- Loop Utama ---
    async def run_loop(self):
        """Background loop: kumpulkan data, deteksi anomali, analisis AI."""

    # --- Collectors ---
    async def _collect_connections(self) -> list[dict]:
        """Ambil koneksi aktif via ss dan parse per-IP."""

    async def _collect_auth_failures(self) -> list[dict]:
        """Parse auth.log: SSH failures per IP."""

    async def _collect_nginx_anomalies(self) -> list[dict]:
        """Parse nginx access.log: error rate, request spike per IP."""

    async def _collect_kernel_stats(self) -> dict:
        """Baca /proc/net/nstat dan /proc/net/sockstat."""

    # --- Aggregation ---
    async def _aggregate(self, raw_data: dict) -> list[dict]:
        """Gabungkan semua sumber data → per-IP stats."""

    async def _update_baseline(self, stats: list[dict]):
        """Update rolling baseline di SQLite."""

    # --- Anomaly Detection (rule-based, tanpa AI) ---
    def _detect_anomalies(self, stats: list[dict]) -> list[ThreatEvent]:
        """Bandingkan stats vs baseline → flag anomali."""

    # --- AI Analysis ---
    async def _analyze_threats(self, threats: list[ThreatEvent]) -> list[ThreatDecision]:
        """Kirim ringkasan ancaman ke Claude → dapat verdict + action."""

    # --- Decision & Action ---
    async def _execute_decision(self, decision: ThreatDecision):
        """Terapkan keputusan: block, throttle, monitor, atau konfirmasi OTP."""

    async def _auto_block(self, ip: str, reason: str, duration_hours: int = 24):
        """Block IP via UFW + catat di pefi_rules."""

    async def _request_confirmation(self, decision: ThreatDecision):
        """Kirim notifikasi Telegram + OTP untuk keputusan Tier 2."""

    # --- Management API (dipanggil dari Telegram commands) ---
    async def get_status(self) -> str:
    async def get_active_threats(self) -> str:
    async def get_active_rules(self) -> str:
    async def whitelist_ip(self, ip: str, reason: str) -> str:
    async def remove_rule(self, ip: str) -> str:
    async def get_report(self, hours: int = 24) -> str:
    async def scan_now(self) -> str:          # trigger analisis manual
```

---

## 6. AI Analysis Tool Schema

Tool baru di `brain.py` khusus untuk PeFi:

```python
PEFI_ANALYSIS_TOOL = {
    "name": "analyze_network_threats",
    "description": (
        "Jarwo menganalisis daftar anomali traffic jaringan dan memutuskan "
        "apakah perlu diblokir, dipantau, atau diabaikan."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ip": {"type": "string"},
                        "verdict": {
                            "type": "string",
                            "enum": ["BLOCK", "THROTTLE", "MONITOR", "IGNORE"]
                        },
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                        "block_duration_hours": {"type": "integer"},
                        "risk_if_wrong": {"type": "string"},
                    },
                    "required": ["ip", "verdict", "confidence", "reason"]
                }
            },
            "summary": {"type": "string"},  # ringkasan situasi untuk notif Telegram
        },
        "required": ["decisions", "summary"]
    }
}
```

**Contoh prompt yang dikirim ke AI:**
```
Konteks server: Ubuntu 22.04, LEMP stack, port terbuka: 22, 80, 443
Baseline normal: ~50 koneksi/menit ke port 80, ~5 SSH attempt/jam

Anomali terdeteksi (5 menit terakhir):
1. IP: 1.2.3.4 (CN) — 847 koneksi ke port 80, 0 ke port lain
   Baseline port 80: 50/menit, sekarang: 169/menit (3.4x)
   Status: tidak di whitelist, belum pernah diblokir
   Riwayat: pertama kali muncul

2. IP: 5.6.7.8 (RU) — coba 34 port berbeda dalam 60 detik
   Pola: sequential port scan (80, 81, 82, ... 443, 8080, 3306)
   Status: pernah diblokir 3 minggu lalu (SSH brute force)

3. IP: 9.10.11.12 (ID) — 23 kali gagal SSH dalam 10 menit
   User-agent: Python-requests/2.28
   Riwayat: clean, tidak pernah diblokir

Berikan verdict untuk setiap IP.
```

---

## 7. Perintah Telegram Baru

| Command | Fungsi | Auth |
|---|---|---|
| `/pefi` | Status PeFi: aktif/nonaktif, statistik 24 jam | Info |
| `/pefi threats` | Daftar ancaman aktif yang sedang dipantau | Info |
| `/pefi rules` | Daftar IP yang diblokir PeFi + TTL | Info |
| `/pefi report` | Laporan analisis AI 24 jam terakhir | Info |
| `/pefi scan` | Trigger analisis manual sekarang | OTP |
| `/pefi whitelist <ip>` | Tambah IP ke whitelist (tidak disentuh PeFi) | OTP |
| `/pefi unblock <ip>` | Hapus blokir PeFi untuk IP tertentu | OTP |
| `/pefi enable` | Aktifkan PeFi | OTP |
| `/pefi disable` | Nonaktifkan PeFi (sementara) | OTP |
| `/pefi autoblock on\|off` | Toggle auto-block Tier 1 | OTP |

---

## 8. Konfigurasi (`config.env`)

```env
# === PeFi — Pre-Emptive Firewall ===
PEFI_ENABLED=true
PEFI_INTERVAL=60                    # detik antar koleksi data
PEFI_AUTO_BLOCK=false               # auto-block Tier 1 tanpa OTP (default: minta konfirmasi)
PEFI_AUTO_BLOCK_CONFIDENCE=0.95     # minimum confidence untuk auto-block

# Threshold anomali (rule-based, sebelum AI)
PEFI_THRESHOLD_CONN_PER_MIN=200     # koneksi/menit dari 1 IP → flag HIGH
PEFI_THRESHOLD_PORT_SCAN=10         # port unik dalam 60 detik → flag PORT_SCAN
PEFI_THRESHOLD_SYN=50               # half-open SYN → flag SYN_FLOOD
PEFI_THRESHOLD_SPIKE_MULTIPLIER=3   # X kali baseline → flag SPIKE

# Baseline
PEFI_BASELINE_DAYS=7                # hari untuk bangun baseline normal
PEFI_BASELINE_MIN_SAMPLES=100       # minimum sample sebelum baseline valid

# Block duration
PEFI_BLOCK_DURATION_HIGH=24         # jam, untuk severity HIGH
PEFI_BLOCK_DURATION_MEDIUM=6        # jam, untuk severity MEDIUM
PEFI_BLOCK_PERMANENT_THRESHOLD=3    # diblokir 3x → permanen

# IP lokal yang otomatis masuk whitelist
PEFI_TRUSTED_NETWORKS=127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

---

## 9. Integrasi dengan SyamAdmin yang Ada

### 9.1 `syamadmin.py` — Wiring
```python
pefi = PreEmptiveFirewall(
    executor=executor,
    firewall=firewall,
    brain=brain,
    notifier=notifier,
    db_path=DB_PATH,
    config=config,
)
modules["pefi"] = pefi

# Jalankan sebagai task asyncio ketiga (parallel dengan bot & monitor)
tasks = [
    bot.run(),
    monitor.run_loop(),
    pefi.run_loop(),           # ← baru
]
await asyncio.gather(*tasks)
```

### 9.2 `modules/firewall.py` — Tambah Method
```python
async def deny_ip_timed(self, ip: str, hours: int, reason: str) -> str:
    """Block IP dengan TTL otomatis — dipakai PeFi untuk block sementara."""

async def get_blocked_ips(self) -> list[str]:
    """Return list IP yang sedang diblokir UFW — untuk PeFi sync."""
```

### 9.3 `modules/monitor.py` — Hook Data
PeFi dan Monitor berbagi beberapa sumber data. Monitor sudah punya `collect_metrics()`. PeFi akan memanggil `executor.run()` langsung untuk data jaringan — tidak duplikasi data metrics CPU/RAM.

### 9.4 `modules/telegram_bot.py` — Command Handler
```python
app.add_handler(CommandHandler("pefi", self.cmd_pefi))
```
`cmd_pefi` adalah router: parse `context.args[0]` → dispatch ke method yang sesuai.

---

## 10. Alur Kerja End-to-End

```
T+00:00  PeFi loop mulai
         ├── collect_connections()     → ss -tnp
         ├── collect_auth_failures()   → tail auth.log
         ├── collect_nginx_anomalies() → tail access.log
         └── collect_kernel_stats()    → /proc/net/*

T+00:02  aggregate() → per-IP stats untuk interval ini

T+00:03  update_baseline() → update rolling average di SQLite

T+00:04  detect_anomalies() → compare vs baseline
         Hasil: [ThreatEvent(ip=1.2.3.4, type=SPIKE, severity=HIGH), ...]

T+00:04  Jika ada ancaman severity ≥ MEDIUM:
         └── analyze_threats() → kirim ringkasan ke Claude API

T+00:05  Claude returns:
         [ThreatDecision(ip=1.2.3.4, verdict=BLOCK, confidence=0.92, ...)]

T+00:05  execute_decision():
         confidence=0.92 < 0.95 → Tier 2 (minta konfirmasi)
         └── notifier.send("⚠️ PeFi: IP 1.2.3.4 terdeteksi SPIKE...")
             Kirim OTP ke Telegram admin

T+00:08  Admin balas OTP
         └── auto_block(1.2.3.4, duration=24h)
             ├── firewall.deny_ip("1.2.3.4")
             ├── INSERT pefi_rules (ip, expires_at, reason)
             └── notifier.send("✅ 1.2.3.4 diblokir 24 jam")

T+60:00  Loop berikutnya — cek juga rule expiry, hapus yang sudah expired
```

---

## 11. Geo-IP (Opsional, Fase 2)

Untuk enrichment data IP dengan informasi negara:

```bash
# Install mmdb-bin (MaxMind GeoLite2 — gratis)
apt install mmdb-bin
# Download database GeoLite2-Country.mmdb
mmdbinspect --db GeoLite2-Country.mmdb 1.2.3.4
```

Atau gunakan API ringan tanpa database lokal:
```python
# ip-api.com — gratis, 45 req/menit, tidak perlu API key
GET http://ip-api.com/json/1.2.3.4?fields=country,isp,org,threat
```

Data geo dipakai AI untuk konteks: "traffic dari CN ke server Indonesia jam 3 pagi — suspicious?"

---

## 12. Urutan Implementasi (Sprint)

### Sprint 1 — Fondasi Data
- [ ] Buat `modules/pefi.py` dengan skeleton class
- [ ] Implementasi `_ensure_db()` (4 tabel baru)
- [ ] Implementasi semua collectors (`_collect_*`)
- [ ] Implementasi `_aggregate()`
- [ ] Unit test collectors di macOS (mock shell output)

### Sprint 2 — Baseline & Anomali
- [ ] Implementasi `_update_baseline()`
- [ ] Implementasi `_detect_anomalies()` (6 rule-based checks)
- [ ] Validasi: run 24 jam di VPS, bangun baseline awal
- [ ] Tuning threshold agar tidak terlalu sensitif

### Sprint 3 — AI Analysis
- [ ] Tambah `PEFI_ANALYSIS_TOOL` di `brain.py`
- [ ] Implementasi `analyze_threats()` di AIBrain
- [ ] Implementasi `_analyze_threats()` di PeFi
- [ ] Test dengan data ancaman simulasi

### Sprint 4 — Action Engine & Telegram
- [ ] Implementasi `_execute_decision()` (Tier 0-3)
- [ ] Implementasi `_auto_block()` + TTL management
- [ ] Implementasi `_request_confirmation()` + OTP flow
- [ ] Tambah command handler `/pefi` di `telegram_bot.py`
- [ ] Semua `/pefi` subcommands

### Sprint 5 — Hardening & Tuning
- [ ] Auto-cleanup expired rules
- [ ] Whitelist otomatis IP lokal/trusted
- [ ] False positive feedback loop (admin bisa mark sebagai FP)
- [ ] Geo-IP enrichment (opsional)
- [ ] Load test: simulasi 10.000 koneksi/menit

---

## 13. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| False positive — blokir IP sah | Admin tidak bisa akses server | Whitelist otomatis IP admin saat init; default Tier 2 (butuh OTP) |
| Overhead CPU dari collectors | Server melambat | Collectors async non-blocking; interval minimal 60 detik; baca /proc bukan tcpdump |
| Biaya AI melonjak | Token Claude terlalu banyak | Anomali dikirim ke AI hanya jika rule-based mendeteksi sesuatu; batching multiple threats dalam satu API call |
| PeFi dimanipulasi (IP spoofing) | Blokir IP yang salah | Tidak block berdasarkan 1 event saja; minimal 3 observasi sebelum verdict |
| DB tumbuh besar | Disk penuh | Pruning otomatis `pefi_ip_stats` setelah 7 hari; retain hanya `pefi_threats` & `pefi_rules` lebih lama |

---

## 14. Metrik Keberhasilan

- **False Positive Rate** < 1% (kurang dari 1 dari 100 block adalah salah)
- **Detection Latency** < 5 menit dari awal serangan sampai notifikasi admin
- **CPU Overhead** < 5% dari total CPU VPS
- **Memory Overhead** < 50 MB tambahan RAM
- **API Cost** < $0.05/hari untuk analisis AI (batching efficient)
