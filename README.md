<p align="center">
  <img src="img/syamadmin.png" alt="SyamAdmin Header" width="100%">
</p>

<p align="center">
  <strong>SyamAdmin v3.0 — AI-powered sysadmin agent for Ubuntu 22.04/24.04 LTS VPS, controlled entirely via Telegram.</strong><br>
  <sub>From zero configuration to secured production-ready LEMP stack and continuous autopilot maintenance.</sub>
</p>

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/quick_start-5_min_setup-00D4AA?style=for-the-badge&logo=rocket&logoColor=white" alt="Quick Start"></a>
  <a href="USER_GUIDE.md"><img src="https://img.shields.io/badge/docs-user_guide-0EA5E9?style=for-the-badge&logo=bookstack&logoColor=white" alt="User Guide"></a>
</p>

<p align="center">
  <!-- Platform & Language -->
  <img src="https://img.shields.io/badge/Ubuntu-22.04_|_24.04_LTS-E95420?style=flat-square&logo=ubuntu&logoColor=white" alt="Ubuntu 22.04/24.04">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Telegram_Bot-API_21-26A5E4?style=flat-square&logo=telegram&logoColor=white" alt="Telegram Bot">
  <img src="https://img.shields.io/badge/Claude_API-Haiku_4.5-6B4FBB?style=flat-square&logo=anthropic&logoColor=white" alt="Claude API">
  <br>
  <!-- Stack -->
  <img src="https://img.shields.io/badge/Nginx-latest-009639?style=flat-square&logo=nginx&logoColor=white" alt="Nginx">
  <img src="https://img.shields.io/badge/MySQL-8.0-4479A1?style=flat-square&logo=mysql&logoColor=white" alt="MySQL 8">
  <img src="https://img.shields.io/badge/PHP-8.3-777BB4?style=flat-square&logo=php&logoColor=white" alt="PHP 8.3">
  <img src="https://img.shields.io/badge/Let's_Encrypt-SSL-003A70?style=flat-square&logo=letsencrypt&logoColor=white" alt="Let's Encrypt">
  <br>
  <!-- Meta -->
  <img src="https://img.shields.io/badge/license-GPL--2.0-22C55E?style=flat-square&logo=gnu&logoColor=white" alt="License GPL-2.0">
  <img src="https://img.shields.io/badge/modules-11-A78BFA?style=flat-square" alt="11 Modules">
  <img src="https://img.shields.io/badge/version-3.0_Memory_Core-F59E0B?style=flat-square" alt="v3.0 Memory Core">
  <img src="https://img.shields.io/badge/PRs-welcome-F472B6?style=flat-square" alt="PRs Welcome">
</p>

---

## Overview

**SyamAdmin** adalah agen sysadmin kecerdasan buatan (*AI sysadmin agent*) mandiri yang berjalan sebagai daemon di latar belakang Ubuntu VPS Anda. SyamAdmin mengotomatiskan pengelolaan server dari instalasi bersih kosong hingga menjadi server produksi hosting LEMP stack yang terkonfigurasi optimal, ter-hardening, dan terpantau 24/7 — dikendalikan seluruhnya melalui chat bot Telegram yang ramah.

Dengan versi **v3.0 Memory Core & Autopilot**, admin awam maupun pemula dapat berinteraksi dengan server dalam bahasa alami (Indonesia/Inggris). AI kini ber-**memori** (mengingat preferensi, riwayat percakapan, dan pelajaran insiden), mampu menyusun & menjalankan **rencana multi-langkah** dari satu kalimat, mendiagnosis kegagalan secara mandiri, merekomendasikan optimasi, menjadwalkan tugas berkala, memandu setup website interaktif, dan melindungi seluruh tindakan kritis lewat **Central OTP Confirmation Flow**. Seluruh keputusan AI memakai **native tool-use** Anthropic (output terstruktur terjamin) dengan model default **Claude Haiku 4.5**.

```
You:  /provision
Bot:  🚀 [1/7] Updating system packages...
      🌐 [2/7] Installing Nginx...
      🗄 [3/7] Installing MySQL 8...
      🐘 [4/7] Installing PHP 8.3...
      🎼 [5/7] Installing Composer...
      🔒 [6/7] Installing Certbot...
      💾 [7/7] Configuring swap...
      ✅ LEMP Stack Installation Complete
      🔑 MySQL root password: xK7#mP...
      🎉 Server siap untuk hosting!

You:  /site wizard
Bot:  🧙‍♂️ Interactive Site Provisioning Wizard
      👉 Langkah 1: Masukkan domain (syamweb.com)
      👉 Langkah 2: Pilih framework (laravel)
      👉 Langkah 3: Buat database MySQL? (ya)
      ⚠️ Ringkasan: syamweb.com | laravel | DB: ya.
      Kirim PIN OTP '4928' untuk mengeksekusi.

You:  /ai backup database, restart nginx, lalu audit keamanan
Bot:  🔄 Autopilot — Rencana Kerja
      ✅ 1/3 Backup database selesai
      ✅ 2/3 Nginx berhasil direstart
      ⏳ 3/3 Menjalankan audit keamanan...
```

---

## 🧠 Fitur Cerdas Unggulan (Advanced Smart AI Features v3.0)

> [!NOTE]
> Seluruh fitur baru dirancang dengan keamanan mutlak dan kemudahan operasional maksimal bagi pengguna yang tidak memiliki latar belakang keahlian teknis Linux (layperson).

### 🛠️ 1. AI Autopilot Troubleshooting & Auto-Repair
Jika ada layanan utama (Nginx, MySQL, PHP-FPM, Fail2Ban, SSH) yang mati mendadak:
- **Deteksi Mandiri**: Monitor mendeteksi crash secara paralel (`asyncio.gather`) setiap interval, langsung mengambil 25 baris log terakhir dari file log atau `journalctl`.
- **Diagnosis AI**: Claude Haiku 4.5 menganalisis log untuk memetakan penyebab utama, solusi awam, perintah perbaikan aman, serta risiko tindakan — dikembalikan dalam JSON terstruktur.
- **Otomatisasi Solusi**: Bot menyuguhkan analisis beserta PIN OTP sekali ketik untuk menjalankan tindakan perbaikan otomatis (*One-Click Repair*). Setelah eksekusi, status service diverifikasi ulang dan ditampilkan.
- Tersedia pula via `/ai perbaiki <service>` secara eksplisit dari chat.

### 📅 2. Natural Language Task Scheduler (AI Cron)
Menjadwalkan pemeliharaan server berkala tanpa perlu pusing dengan baris sintaks cron:
- Menerima perintah bebas bahasa alami (misal: *"jalankan backup db setiap senin jam 3 pagi"* atau *"audit keamanan tiap hari minggu jam 11 malam"*).
- Claude mem-parsing waktu ke dalam ekspresi cron Linux standar secara otomatis (`0 3 * * 1`).
- Mendukung tugas: `backup_all`, `backup_db`, `backup_files`, `security_audit`, `rkhunter_scan`.
- Ditulis ke dalam crontab pengguna secara aman via file temp dan deduplication — bebas dari korupsi data cron.

### 📊 3. Smart Resource Optimization Advisor
Menghentikan pemborosan RAM, CPU, dan Swap file secara berkala:
- Mengagregasikan statistik historis penggunaan sumber daya server selama 7 hari dari SQLite (rata-rata & puncak CPU, RAM, Disk, Load).
- AI menganalisis tren performa dan menyusun laporan terperinci berisi usulan tuning konfigurasi layanan (Swap, Nginx, MySQL buffer pool, PHP-FPM pool max children).
- Tuning optimal dapat langsung diterapkan secara instan melalui gerbang OTP dinamis.

### 🌐 4. Guided Interactive Website Setup Wizard
Memandu pembuatan website baru langkah-demi-langkah secara bertahap:
- **Conversation State Machine** (DOMAIN → TYPE → DB → CONFIRM): Bot membimbing admin mengisi Domain ➔ Pilihan Framework (`laravel`, `wordpress`, `default`) ➔ Kebutuhan Database MySQL.
- Wizard timeout otomatis 10 menit — tidak memblokir perintah lain.
- **Automated Provisioning**: Otomatis membangun vhost Nginx (IPv4/IPv6 adaptive), PHP-FPM pool terisolasi per-situs, membuat database & kredensial MySQL baru berkekuatan tinggi (`token_urlsafe`), mengonfigurasi SSL Let's Encrypt, serta menyajikan rangkuman login siap pakai.
- Fallback auto-diagnosis certbot (DNS, port, rate limit, unauthorized) dengan panduan perbaikan.

### 🛡️ 5. AI Security Threat Scanner & SSH Port Tuner
Melindungi server dari serangan brute-force dan eksploitasi eksternal:
- **Pemindai Keamanan**: Menganalisis Fail2Ban status serta berkas log `/var/log/auth.log` secara berkala untuk memetakan alamat IP penyerang, asal negara penyerang terbanyak, dan port yang ditargetkan dalam laporan eksekutif AI.
- **Port SSH Tuner 5-Lapis** (`/harden_ssh_port <PORT>`): Memindahkan port SSH default 22 ke port kustom non-standar dengan verifikasi ketat:
  1. Validasi rentang port (1024-65535) & benturan dengan service LEMP (3306, 80, 443, 8080, 9000).
  2. Buka port baru secara otomatis di firewall UFW.
  3. Backup & tulis ulang konfigurasi SSHD dengan regex-safe replace.
  4. Uji kelayakan sintaks (`sshd -t`). Rollback otomatis jika gagal.
  5. Restart & verifikasi port internal (`ss -tlnp`). Jika gagal → rollback & hapus UFW rule baru.
  6. Hapus port lama dari firewall UFW.
- **SSH Hardening Self-Healing**: Pattern-match error SSHD (missing config.d, duplicate directives, missing privilege dir, deprecated options) dengan auto-fix & retry loop.

### 💰 6. Claude API Token Utilization Statistics
- Memantau volume input/output token Claude Haiku 4.5 secara real-time di SQLite.
- Melacak total pemanggilan API dan menghitung estimasi biaya riil penggunaan AI dalam mata uang USD dan IDR (`Rp`) langsung di ruang obrolan Telegram melalui perintah `/token`.
- Tarif default: Input $1/1M token, Output $5/1M token (Claude Haiku 4.5). Rate USD/IDR: Rp16.300.

### 🧩 7. Multi-Step AI Orchestrator (Autopilot)
Satu kalimat majemuk → serangkaian aksi berurutan yang dieksekusi otomatis dan transparan:
- AI memecah perintah seperti *"backup database, lalu restart nginx, terakhir ubah port SSH ke 2222"* menjadi rencana langkah-demi-langkah terstruktur (native tool-use `steps[]`).
- **Live Progress Tracker**: satu pesan status yang terus diperbarui (✅ selesai / ⏳ berjalan / 💤 menunggu / ❌ gagal).
- **Halt-on-failure**: jika satu langkah gagal, sisa langkah dibatalkan otomatis dan AI menjelaskan penyebabnya.
- **Single-flight guard**: perintah baru ditolak selama plan masih berjalan.
- **Gerbang OTP terpadu**: bila ada langkah berisiko (bukan allowlist `SAFE_READONLY_ACTIONS`), seluruh rencana wajib satu OTP.
- **Learn on success**: setelah plan berhasil, ringkasan dicatat ke long-term memory (Pilar 4) agar bisa diambil relevan di masa depan.

### 💾 8. Persistent Memory Core (Quad-Core Memory)
Agen kini ber-memori, bukan sekadar reaktif — berbasis SQLite:
- **Pilar 1 (Token Log)**: Setiap panggilan Claude dicatat di tabel `token_usage` (aksi, input/output token, model, timestamp).
- **Pilar 2 (User Preferences)**: Preferensi admin (versi PHP, timezone, dll.) disimpan permanen di `user_memory`.
- **Pilar 3 (Chat History)**: Sliding window 8 turn terakhir dikirim ke AI sebagai konteks multi-giliran.
- **Pilar 4 (Long-Term Memory + FTS5)**: Pelajaran insiden & rencana sukses dicatat di `long_term_memory`, dapat dicari relevan via SQLite **FTS5** full-text search (fallback LIKE jika FTS5 tak tersedia).
- **Redaksi rahasia otomatis**: password/token/API key disensor (`[REDACTED]`) sebelum disimpan ke memori.
- **Retention otomatis**: metrics (30 hari), audit log (90 hari), chat history (14 hari), long_term_memory (max 1000 baris) — dipangkas sekali per 24 jam.

### 🔧 9. AI Error Explanation (Augmented Failure)
- Setiap kegagalan operasi (SSL, restore, site add, plan step) otomatis diperkaya dengan penjelasan ramah-pemula dari AI.
- Model mengubah pesan error teknis menjadi deskripsi sederhana + 1-2 langkah perbaikan dalam bahasa Indonesia.

### 🌍 10. IPv6 Auto-Detection & Adaptive Nginx Config
- Sebelum menulis konfigurasi Nginx (provisioning maupun add_site), agen mendeteksi apakah kernel VPS mendukung IPv6 (`sysctl` + `ip addr`).
- Template vhost dipilih otomatis: **IPv4+IPv6** (`listen [::]:80`) atau **IPv4-only** untuk VPS minimal/container yang menonaktifkan IPv6.
- Auto-fix loop pada `nginx -t` untuk menghapus IPv6 directive yang menyebabkan error.

### 🧭 11. Server Onboarding Setup Wizard (`/setup`)
- Panduan interaktif langkah-demi-langkah untuk pemula yang baru mendapatkan VPS bersih.
- Mendeteksi otomatis server baru (LEMP belum terpasang) dan menawarkan shortcut `/setup` saat `/start`.
- Tiga jalur: pasang LEMP → amankan server (hardening menyeluruh) → buat website pertama.

---

## 🏗 Arsitektur Sistem

```
┌──────────────────────────────────────────────┐
│                  Telegram Bot                │  ← Kendali Utama Admin via Chat
│  (NLP Free-Text Handler + Wizard State Mach) │
│  19 command handlers + free-text fallback    │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│                  AI Brain                    │  ← Claude Haiku 4.5 (Native Tool-Use)
│  Memory Core · Planner · Troubleshoot · Scan │
│  Prompt Caching (ephemeral) · Token Tracker  │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│        Command Router & Safety Filter        │  ← Menolak perintah destruktif
│        (Central OTP Confirmation Core)       │  ← BLOCKED_PATTERNS_REGEX + shlex
└──┬───────────┬───────────┬───────────┬───────┘
   │           │           │           │
   ▼           ▼           ▼           ▼
┌─────┐     ┌─────┐     ┌─────┐     ┌──────┐
│Prov │     │Sec  │     │Fire │     │Site  │
│isio │     │uri  │     │wall │     │Mana  │  ➔ Backup · Notifier · Executor
│ner  │     │ty   │     │     │     │ger   │
└─────┘     └─────┘     └─────┘     └──────┘
   │           │           │           │
   ▼           ▼           ▼           ▼
┌──────────────────────────────────────────────┐
│          Ubuntu VPS Managed Services         │
│  Nginx · MySQL 8 · PHP 8.3-FPM · UFW · SSHD │
│  Fail2Ban · Let's Encrypt · Certbot          │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│               SQLite Database                │
│  audit_log · metrics · sites · alerts        │
│  token_usage · user_memory · chat_history    │
│  long_term_memory + FTS5 · scheduled_tasks   │
└──────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Details |
|-------------|---------|
| **Server** | Ubuntu 22.04 LTS atau 24.04 LTS VPS (min 1 GB RAM, 1 vCPU, 20 GB disk) |
| **Access** | Root SSH access |
| **Telegram** | Bot token dari [@BotFather](https://t.me/BotFather), Admin User ID dari [@userinfobot](https://t.me/userinfobot) |
| **AI (Claude)** | [Anthropic API key](https://console.anthropic.com) untuk modul NLP (opsional tapi direkomendasikan) |

### Installation

**Opsi A — Unduh langsung dari GitHub di server (paling cepat):**

```bash
# 1. SSH ke server, buat folder kerja, lalu unduh tarball dari repo
ssh root@IP_SERVER_ANDA
mkdir -p ~/syamadmin && cd ~/syamadmin
wget https://raw.githubusercontent.com/Syamsuddin/SyamAdmin/main/syamadmin.tar.gz
# alternatif: curl -LO https://raw.githubusercontent.com/Syamsuddin/SyamAdmin/main/syamadmin.tar.gz

# 2. Ekstrak (arsip flat → file langsung di folder ini) & jalankan installer
tar xzf syamadmin.tar.gz
chmod +x install.sh
sudo ./install.sh

# 3. Konfigurasi kredensial (Wajib sebelum memulai)
sudo nano /etc/syamadmin/config.env
```

> Catatan: metode `wget` di atas berlaku untuk repo **publik**. Jika repo privat,
> gunakan `git clone https://<TOKEN>@github.com/Syamsuddin/SyamAdmin.git` atau salin via `scp` (Opsi B).

**Opsi B — Build lokal lalu salin via `scp`:**

```bash
# Dari komputer lokal (lihat perintah build tarball di CLAUDE.md):
scp syamadmin.tar.gz root@IP_SERVER_ANDA:~/syamadmin/
# lalu di server: cd ~/syamadmin && tar xzf syamadmin.tar.gz && sudo ./install.sh
```

Isi variabel utama di dalam config file:

```env
# Wajib
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_ID=987654321

# Direkomendasikan (untuk fitur AI penuh)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
CLAUDE_MODEL=claude-haiku-4-5-20251001   # default, bisa diganti

# Identitas & Tuning
SERVER_NAME=my-vps-production
SERVER_TIMEZONE=Asia/Makassar
SSH_PORT=22

# Thresholds Alert
ALERT_THRESHOLD_CPU=85
ALERT_THRESHOLD_RAM=90
ALERT_THRESHOLD_DISK=85
ALERT_THRESHOLD_LOAD=4.0
MONITOR_INTERVAL=60          # detik antar pemantauan

# Backup
BACKUP_DIR=/var/backups/syamadmin
BACKUP_RETENTION_DAYS=7

# PHP Version
PHP_VERSION=8.3

# Retention DB otomatis
METRICS_RETENTION_DAYS=30
AUDIT_RETENTION_DAYS=90
CHAT_HISTORY_RETENTION_DAYS=14
LONG_TERM_MEMORY_MAX_ROWS=1000
```

```bash
# 4. Aktifkan daemon SyamAdmin
sudo systemctl enable --now syamadmin

# 5. Cek status
sudo systemctl status syamadmin
sudo journalctl -u syamadmin -f

# 6. Buka Telegram dan kirim perintah /start ke bot Anda! 🎉
```

---

## 📱 Telegram Commands Reference

### 🤖 Fitur Cerdas (AI & Advanced v3.0)

| Command | Deskripsi | Protokol Keamanan |
|---------|-------------|-------------------|
| `/ai <perintah bebas>` | Perintah bahasa alami; AI memilih aksi tunggal ATAU menyusun rencana multi-langkah (autopilot) | OTP untuk aksi/rencana berisiko |
| `/site wizard` | Membuka panduan interaktif langkah-demi-langkah setup website + DB + SSL | **OTP Dinamis** sebelum eksekusi |
| `/security_report` | Mengurai Fail2Ban & auth.log, AI menyusun laporan ancaman eksekutif | Informasi (Aman langsung) |
| `/harden_ssh_port <PORT>` | Memindahkan port SSH default ke port non-standar pilihan Anda (5-layer safety check) | **OTP + 5-Layer Connection Test** |
| `/optimize` | Menganalisis log metrik 7 hari, merekomendasikan tuning performa LEMP | **OTP Dinamis** sebelum eksekusi |
| `/cron <Perintah Bebas>` | Menjadwalkan tugas berkala dengan instruksi bahasa alami | **OTP Dinamis** sebelum eksekusi |
| `/token` | Menampilkan statistik kuota token Claude API dan biaya riil (USD & IDR) | Informasi (Aman langsung) |

### 🖥 Perintah Utama (Core System)

| Command | Deskripsi |
|---------|-------------|
| `/start` | Mulai bot; deteksi otomatis server baru & tawarkan `/setup` |
| `/status` | Dashboard lengkap: identitas server & IP (lokal+publik), resource bar, status layanan, firewall & port listen, Fail2Ban, web stack, AI engine, & Memory Core |
| `/services` | Memeriksa status kesehatan dari semua managed service (nginx, mysql, php8.3-fpm, fail2ban, ufw, ssh) |
| `/setup` | Memulai wizard interaktif onboarding server langkah-demi-langkah |
| `/provision` | Menginstall penuh LEMP Stack 7-langkah (Update → Nginx → MySQL 8 → PHP 8.3 + 14 ext → Composer → Certbot → Swap 2GB) | OTP |
| `/logs [service]` | Membaca 30 baris log terakhir; service: `nginx`, `mysql`, `auth`, `syslog`, `fail2ban` (whitelist anti path-traversal) |
| `/audit` | Melihat 15 entri riwayat eksekusi shell terbaru yang dicatat oleh Command Executor |
| `/backup` | Full backup: database MySQL (all-databases, single-transaction, gzip) + web files (tar.gz) |
| `/backup db` | Backup databases saja; pre-check MySQL aktif, verifikasi ukuran file |
| `/backup files` | Backup `/var/www`, `/etc/nginx`, `/etc/php` |
| `/backup list` | Menampilkan 20 backup terbaru beserta ukuran dan tanggal |
| `/restore <file>` | Memulihkan data dari file backup `.sql.gz` atau `.tar.gz` (OTP + path-traversal protection) |
| `/help` | Bantuan lengkap |

### 🌐 Virtual Host & SSL

| Command | Deskripsi |
|---------|-------------|
| `/site add domain.com` | Membuat vhost Nginx, direktori publik, dan pool PHP-FPM terisolasi (IPv6 adaptive) |
| `/site add app.com laravel` | Menambahkan situs dengan konfigurasi root Laravel (`/public`) |
| `/site add app.com wordpress` | Menambahkan situs dengan konfigurasi WordPress |
| `/site ssl domain.com` | Mengaktifkan HTTPS SSL Let's Encrypt dengan auto-renewal (certbot.timer / crontab fallback) |
| `/site list` | Menampilkan daftar situs aktif beserta status SSL dari database |
| `/site remove domain.com` | Menghapus Nginx vhost situs; **direktori data tetap disimpan** demi keamanan | OTP |
| `/site wizard` | Wizard interaktif setup website (domain → framework → DB → OTP) |

### 🔒 Keamanan & Firewall

| Command | Deskripsi |
|---------|-------------|
| `/security` | Menjalankan audit keamanan komprehensif: SSH config, root login, Fail2Ban, UFW, unattended-upgrades, open ports, pending updates, recent logins |
| `/security_report` | Laporan AI ancaman keamanan dari auth.log + Fail2Ban |
| `/harden` | Hardening menyeluruh: SSH self-healing + Fail2Ban (nginx-aware jails) + Firewall UFW + Auto-update |
| `/harden_ssh_port <PORT>` | Pindah port SSH dengan 5-layer safety (validate → UFW → config → sshd-test → verify) | OTP |
| `/firewall` | Menampilkan status dan aturan firewall UFW verbose |
| `/fw allow <PORT>` | Membuka akses port tertentu pada firewall UFW |
| `/fw deny <PORT>` | Menutup port; proteksi khusus jika menutup port SSH aktif | OTP jika port SSH |
| `/fw rules` | Menampilkan list aturan firewall bernomor |
| `/confirm <OTP>` | Konfirmasi aksi berisiko dengan kode OTP 4-digit |

---

## 🔒 Model Keamanan Lapis Ganda (Dual-Layer Security Model)

### 1. Central OTP Confirmation Gate
Setiap tindakan kritis yang bersifat destruktif atau mengubah konfigurasi sistem dilindungi oleh **PIN OTP 4-digit dinamis** yang aman secara kriptografi (`secrets.randbelow`):
- Memiliki waktu kedaluwarsa ketat selama **60–120 detik** (tergantung jenis aksi).
- Admin dapat menyetujui dengan `/confirm <OTP>` atau cukup membalas OTP-nya langsung di chat.
- Aksi destruktif (`provision`, `remove_site`, `deny_ssh`, `change_ssh_port`, `restore`, `repair_service`, `wizard_provision`) **menolak kata afirmatif** seperti `ya/ok` — wajib kode OTP numerik.
- Kata afirmatif (`ya`, `iya`, `ok`, `oke`, `yes`, `y`, `lanjut`, `setuju`, `gas`) hanya berlaku untuk aksi non-destruktif.

### 2. Safety Filter & Tokenized shlex
Setiap baris perintah shell yang dieksekusi oleh Executor disaring secara ketat melalui dua lapisan:
- **Regex BLOCKED_PATTERNS_REGEX**: `rm -rf /` (beserta bypass spasi ganda), `mkfs.*`, `dd of=/dev/sd*`, `chmod 777 /`, `curl/wget | bash`, `| bash`, `base64 | bash`, fork bomb.
- **shlex Tokenizer**: Parsing token untuk mendeteksi `rm -rf` ke path kritis, chaining shell interpreter (`| bash`), nested `bash -c` dengan argumen berbahaya.
- Setiap perintah yang dieksekusi (atau diblokir) dicatat ke `audit_log` SQLite dengan timestamp, module, action, status, dan durasi.

### 3. Prompt Caching (Cost Optimization)
- System prompt & tool definition bertanda `cache_control: ephemeral` agar tidak ditagih penuh tiap panggilan `/ai`. Efektif bila prefix ≥ minimum token model (Haiku: 2048).

---

## 📂 Struktur Proyek

```
syamadmin/
├── install.sh                  # One-click installer sistem (Ubuntu 22.04/24.04)
├── config.env.example          # Template konfigurasi lingkungan (20+ variabel)
├── syamadmin.py                # Entry point utama daemon agen (asyncio)
├── syamadmin.service           # Unit file Systemd (auto-restart, logrotate)
├── USER_GUIDE.md               # Panduan lengkap operasional (ID/EN)
│
├── modules/
│   ├── telegram_bot.py         # Telegram Interface (19 cmd + wizard state machine + OTP gate)
│   ├── brain.py                # AI Decision Engine (Claude API + tool-use + Memory Core)
│   ├── provisioner.py          # LEMP Stack Installer 7-langkah + IPv6 adaptive Nginx
│   ├── security.py             # SSH Hardening (self-healing) + Fail2Ban + Audit + SSH Port Tuner
│   ├── firewall.py             # UFW manager (allow/deny/list/rate_limit/IP rules)
│   ├── monitor.py              # System Monitor (psutil) + threshold alerts + service crash detector
│   ├── site_manager.py         # Nginx VHost + SSL Let's Encrypt + PHP Pool + IPv6 adaptive
│   ├── backup.py               # MySQL dump (gzip, verify) + file tar + restore + retention
│   ├── notifier.py             # Telegram alert dengan deduplication & cooldown
│   └── executor.py             # Safe Shell Executor (regex+shlex filter, audit log, add_cron_job)
│
├── scripts/
│   ├── collect_trends.py       # Pengumpul tren metrik harian ke SQLite
│   ├── cron_job.py             # Task Runner aman untuk eksekusi berkala cron job
│   ├── harden_ssh.sh           # Skrip hardening SSH manual
│   ├── setup_fail2ban.sh       # Setup Fail2Ban manual
│   └── setup_swap.sh           # Pembuat swap memori otomatis
│
├── templates/
│   ├── nginx_ssl.conf          # Template Nginx + SSL
│   ├── nginx_vhost.conf        # Template Nginx vhost dasar
│   └── php_fpm_pool.conf       # Template PHP-FPM pool per-site
│
└── syamadmin.tar.gz            # Paket rilis siap-deploy
```

---

## 🗄 Database Schema (SQLite)

SyamAdmin menggunakan satu file SQLite (`/var/lib/syamadmin/syamadmin.db`) dengan tabel-tabel berikut:

| Tabel | Fungsi |
|-------|--------|
| `audit_log` | Setiap perintah shell yang dieksekusi (module, action, status, duration) |
| `metrics` | Metrik historis CPU/RAM/Disk/Load per interval monitor |
| `sites` | Daftar website terkelola (domain, root_path, ssl_enabled, status) |
| `alerts` | Riwayat alert yang dikirim (severity, module, message) |
| `scheduled_tasks` | Daftar tugas terjadwal (task_type, schedule, config) |
| `token_usage` | Log konsumsi token Claude API (input, output, model) |
| `user_memory` | Preferensi admin persisten (key-value) |
| `chat_history` | Riwayat percakapan sliding window (role, content, redacted) |
| `long_term_memory` | Pelajaran insiden & rencana sukses (category, summary) |
| `long_term_fts` | FTS5 virtual table untuk pencarian cepat long_term_memory |

---

## 🗺 Roadmap

- [x] Scheduled task with natural language cron expression (via `/cron` NLP Scheduler)
- [x] Automated performance tuning recommendations (via `/optimize` Advisor)
- [x] Native tool-use AI routing (structured output, no fragile JSON parsing)
- [x] Multi-step AI orchestrator with live progress & halt-on-failure
- [x] Persistent Memory Core (preferences, chat history, incident lessons via FTS5)
- [x] AI Error Explanation (augmented failure messages in Bahasa Indonesia)
- [x] IPv6 auto-detection & adaptive Nginx config
- [x] Self-healing provisioner & SSH hardening (pattern-match + auto-fix + retry)
- [x] Server onboarding setup wizard (`/setup`)
- [x] Prompt caching for Claude API cost optimization
- [x] Database retention policy (metrics, audit, chat, long-term memory)
- [ ] Docker container monitoring integration
- [ ] Webhook support for CI/CD pipelines
- [ ] Web dashboard (localhost) for visual metrics
- [ ] Multi-admin support with role-based permissions
- [ ] Integration with external monitoring (Uptime Kuma, Grafana)
- [ ] Multi-server management from a single bot

---

## 🤝 Contributing

Kontribusi selalu terbuka! Jangan ragu untuk mengirimkan Pull Request ke repositori ini.

1. Fork repositori
2. Buat branch fitur Anda (`git checkout -b feature/amazing-feature`)
3. Commit perubahan Anda (`git commit -m 'Add amazing feature'`)
4. Push ke branch Anda (`git push origin feature/amazing-feature`)
5. Ajukan Pull Request

---

## 📄 License

Proyek ini dilisensikan di bawah **GNU General Public License v2.0** — lihat berkas [LICENSE](LICENSE) untuk detail lebih lanjut.

---

<p align="center">
  <sub>Built with ☕ for sysadmins who'd rather chat than SSH.</sub><br>
  <sub>Made with ❤️ in Kalimantan, Indonesia 🇮🇩</sub>
</p>
