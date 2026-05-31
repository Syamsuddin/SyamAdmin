<p align="center">
  <img src="img/syamadmin.png" alt="SyamAdmin Header" width="100%">
</p>

<p align="center">
  <strong>SyamAdmin v3.0 — AI-powered sysadmin agent for Ubuntu 22.04 LTS VPS, controlled entirely via Telegram.</strong><br>
  <sub>From zero configuration to secured production-ready LEMP stack and continuous autopilot maintenance.</sub>
</p>

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/quick_start-5_min_setup-00D4AA?style=for-the-badge&logo=rocket&logoColor=white" alt="Quick Start"></a>
  <a href="USER_GUIDE.md"><img src="https://img.shields.io/badge/docs-user_guide-0EA5E9?style=for-the-badge&logo=bookstack&logoColor=white" alt="User Guide"></a>
</p>

<p align="center">
  <!-- Platform & Language -->
  <img src="https://img.shields.io/badge/Ubuntu-22.04_LTS-E95420?style=flat-square&logo=ubuntu&logoColor=white" alt="Ubuntu 22.04">
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
Bot:  🚀 Installing LEMP stack...
      ✅ Nginx installed
      ✅ MySQL 8 secured (password: xK7#mP...)
      ✅ PHP 8.3 + 15 extensions configured
      ✅ Certbot ready
      🎉 Server siap untuk hosting!

You:  /site wizard
Bot:  🧙‍♂️ Interactive Site Setup Wizard started...
      👉 Langkah 1: Masukkan domain (syamweb.com)
      👉 Langkah 2: Pilih framework (laravel)
      👉 Langkah 3: Buat database MySQL? (ya)
      ⚠️ Ringkasan: syamweb.com | laravel | DB: ya.
      Kirim PIN OTP '4928' untuk mengeksekusi.
```

---

## 🧠 Fitur Cerdas Unggulan (Advanced Smart AI Features v3.0)

> [!NOTE]
> Seluruh fitur baru dirancang dengan keamanan mutlak dan kemudahan operasional maksimal bagi pengguna yang tidak memiliki latar belakang keahlian teknis Linux (layperson).

### 🛠️ 1. AI Autopilot Troubleshooting & Auto-Repair
Jika ada layanan utama (Nginx, MySQL, PHP-FPM) yang mati mendadak:
- **Deteksi Mandiri**: Monitor mendeteksi crash secara langsung dan mengambil 50 baris berkas log terakhir.
- **Diagnosis AI**: Claude Haiku 4.5 menganalisis log untuk memetakan penyebab utama, solusi awam, serta risiko tindakan.
- **Otomatisasi Solusi**: Bot menyuguhkan analisis beserta PIN OTP sekali ketik untuk menjalankan tindakan perbaikan otomatis (*One-Click Repair*).

### 📅 2. Natural Language Task Scheduler (AI Cron)
Menjadwalkan pemeliharaan server berkala tanpa perlu pusing dengan baris sintaks cron:
- Menerima perintah bebas bahasa alami admin (misal: *"jalankan backup db setiap senin jam 3 pagi"* atau *"audit keamanan tiap hari minggu jam 11 malam"*).
- Claude mem-parsing waktu ke dalam ekspresi cron Linux standar secara otomatis (`0 3 * * 1`).
- Ditulis ke dalam crontab pengguna secara aman dan diuji sintaksisnya agar bebas dari korupsi data cron.

### 📊 3. Smart Resource Optimization Advisor
Menghentikan pemborosan RAM, CPU, dan Swap file secara berkala:
- Mengagregasikan statistik historis penggunaan sumber daya server selama 7 hari ke belakang.
- AI menganalisis tren performa dan menyusun laporan terperinci berisi usulan tuning konfigurasi layanan (Swap, Nginx, MySQL buffer pool, PHP-FPM pool max children).
- Tuning optimal dapat langsung diterapkan secara instan melalui gerbang OTP dinamis.

### 🌐 4. Guided Interactive Website Setup Wizard
Memandu pembuatan website baru langkah-demi-langkah secara bertahap:
- **Conversation State Machine**: Bot membimbing admin mengisi Domain ➔ Pilihan Framework (Laravel, WordPress, Default HTML/PHP) ➔ Kebutuhan Database MySQL.
- **Automated Provisioning**: Otomatis membangun vhost Nginx, PHP pool terisolasi, membuat database & kredensial MySQL baru berkekuatan tinggi, mengonfigurasi SSL Let's Encrypt, serta menyajikan rangkuman login siap pakai.

### 🛡️ 5. AI Security Threat Scanner & SSH Port Tuner
Melindungi server dari serangan brute-force dan eksploitasi eksternal:
- **Pemindai Keamanan**: Menganalisis Fail2Ban status serta berkas log `/var/log/auth.log` secara berkala untuk memetakan alamat IP penyerang, asal negara penyerang terbanyak, dan port yang ditargetkan dalam laporan eksekutif.
- **Port SSH Tuner 4-Lapis**: Memindahkan port SSH default 22 ke port kustom non-standar dengan verifikasi ketat:
  1. Validasi rentang port (1024-65535) & bentrokan dengan service LEMP.
  2. Buka port baru secara otomatis di firewall UFW.
  3. Uji kelayakan sintaks berkas konfigurasi baru (`sshd -t`). Rollback otomatis jika gagal.
  4. Restart dan verifikasi keaktifan port internal (`ss -tlnp`). Jika gagal, kembalikan ke port lama.
  5. Hapus port lama 22 dari firewall UFW.

### 💰 6. Claude API Token Utilization Statistics
- Memantau volume input/output token Claude Haiku 4.5 secara real-time.
- Melacak total pemanggilan API dan menghitung estimasi biaya riil penggunaan AI dalam mata uang USD dan IDR (`Rp`) langsung di ruang obrolan Telegram melalui perintah `/token`.

### 🧩 7. Multi-Step AI Orchestrator (Autopilot)
Satu kalimat majemuk → serangkaian aksi berurutan yang dieksekusi otomatis dan transparan:
- AI memecah perintah seperti *"backup database, lalu restart nginx, terakhir ubah port SSH ke 2222"* menjadi rencana langkah-demi-langkah terstruktur (native tool-use).
- **Live Progress Tracker**: satu pesan status yang terus diperbarui (✅ selesai / ⏳ berjalan / 💤 menunggu).
- **Halt-on-failure**: jika satu langkah gagal, sisa langkah dibatalkan dan AI menjelaskan penyebabnya — tidak ada eksekusi membabi buta.
- **Gerbang OTP terpadu**: bila ada langkah berisiko, seluruh rencana wajib satu OTP (kata "ya" ditolak).

### 💾 8. Persistent Memory Core (Quad-Core Memory)
Agen kini ber-memori, bukan sekadar reaktif:
- **Preferensi admin** (versi PHP, timezone) diingat permanen.
- **Riwayat percakapan** (sliding window) untuk konteks multi-giliran.
- **Pelajaran insiden** dicatat tiap rencana sukses & dicari relevan via SQLite **FTS5**.
- **Redaksi rahasia otomatis**: password/token/API key disensor sebelum disimpan ke memori.

---

## 🏗 Arsitektur Sistem

```
┌──────────────────────────────────────────────┐
│                  Telegram Bot                │  ← Kendali Utama Admin via Chat
│  (NLP Free-Text Handler + Wizard State Mach) │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│                  AI Brain                    │  ← Claude Haiku 4.5 (Tool-Use)
│  Memory Core · Planner · Troubleshoot · Scan │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│        Command Router & Safety Filter        │  ← Menolak perintah destruktif
│        (Central OTP Confirmation Core)       │
└──┬───────────┬───────────┬───────────┬───────┘
   │           │           │           │
   ▼           ▼           ▼           ▼
┌─────┐     ┌─────┐     ┌─────┐     ┌──────┐
│Prov │     │Sec  │     │Fire │     │Site  │
│isio │     │uri  │     │wall │     │Mana  │  ➔ Backup, Notifier, Executor
│ner  │     │ty   │     │     │     │ger   │
└─────┘     └─────┘     └─────┘     └──────┘
   │           │           │           │
   ▼           ▼           ▼           ▼
┌──────────────────────────────────────────────┐
│          Ubuntu VPS Managed Services         │
│  Nginx · MySQL 8 · PHP-FPM · UFW · SSHD      │
│  Fail2Ban · Let's Encrypt · Certbot          │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│               SQLite Database                │
│  Sites · Metrics · Audit · Token · Memory    │
│  (user_memory · chat_history · long_term+FTS)│
└──────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Details |
|-------------|---------|
| **Server** | Ubuntu 22.04 LTS VPS (min 1 GB RAM, 1 vCPU, 20 GB disk) |
| **Access** | Root SSH access |
| **Telegram** | Bot token dari [@BotFather](https://t.me/BotFather), Admin User ID dari [@userinfobot](https://t.me/userinfobot) |
| **AI (Claude)** | [Anthropic API key](https://console.anthropic.com) untuk modul NLP |

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
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_ID=987654321
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx   # Kunci API Claude untuk fitur cerdas
SERVER_NAME=my-vps-production
```

```bash
# 4. Aktifkan daemon SyamAdmin
sudo systemctl enable --now syamadmin

# 5. Buka Telegram dan kirim perintah /start ke bot Anda! 🎉
```

---

## 📱 Telegram Commands Reference

### Fitur Cerdas (AI & Advanced v2.0)

| Command | Deskripsi | Protokol Keamanan |
|---------|-------------|-------------------|
| `/ai <perintah bebas>` | Perintah bahasa alami; AI memilih aksi tunggal ATAU menyusun rencana multi-langkah (autopilot) | OTP untuk aksi/rencana berisiko |
| `/site wizard` | Membuka panduan interaktif langkah-demi-langkah setup website + DB | **OTP Dinamis** sebelum eksekusi |
| `/security_report` | Mengurai Fail2Ban & auth.log, AI menyusun laporan ancaman eksekutif | Informasi (Aman langsung) |
| `/harden_ssh_port <PORT>` | Memindahkan port SSH default ke port non-standar pilihan Anda | **OTP + 4-Layer Connection Test** |
| `/optimize` | Menganalisis log metrik 7 hari, merekomendasikan tuning performa LEMP | **OTP Dinamis** sebelum eksekusi |
| `/cron <Perintah Bebas>` | Menjadwalkan tugas berkala dengan instruksi bahasa alami | **OTP Dinamis** sebelum eksekusi |
| `/token` | Menampilkan statistik kuota token Claude API dan biaya riil (USD & IDR) | Informasi (Aman langsung) |

### Perintah Utama (Core System)

| Command | Deskripsi |
|---------|-------------|
| `/status` | Dashboard lengkap: identitas server & IP (lokal+publik), resource, status layanan, firewall & port terbuka, Fail2Ban, web stack, AI engine, & Memory Core |
| `/services` | Memeriksa status kesehatan dari semua managed service |
| `/setup` | Memulai wizard interaktif panduan setup server langkah-demi-langkah |
| `/provision` | Menginstall penuh LEMP Stack (Nginx, MySQL, PHP 8.3, Certbot) (OTP) |
| `/logs [service]` | Membaca 30 baris log terakhir (nginx, mysql, fail2ban, auth, syslog) |
| `/audit` | Melihat riwayat eksekusi shell yang dicatat oleh Command Executor |
| `/backup` | Membuat arsip backup untuk database MySQL dan web files |
| `/restore <file>` | Memulihkan data dari file backup (.sql.gz/.tar.gz) (OTP proteksi) |

### Virtual Host & SSL

| Command | Deskripsi |
|---------|-------------|
| `/site add domain.com` | Membuat vhost Nginx, direktori publik, dan pool PHP-FPM terisolasi |
| `/site add app.com laravel` | Menambahkan situs baru dengan konfigurasi root folder Laravel (`/public`) |
| `/site ssl domain.com` | Mengaktifkan HTTPS SSL Let's Encrypt dengan perpanjangan otomatis |
| `/site list` | Menampilkan daftar situs aktif beserta status SSL |
| `/site remove domain.com` | Menghapus Nginx vhost situs (direktori data tetap disimpan demi keamanan) |

### Keamanan & Firewall

| Command | Deskripsi |
|---------|-------------|
| `/security` | Menjalankan audit keamanan komprehensif pada server |
| `/harden` | Pengamanan total: Hardening SSH + instalasi Fail2Ban + Firewall + Auto Update |
| `/firewall` | Menampilkan status dan aturan firewall UFW yang aktif |
| `/fw allow <PORT>` | Membuka akses port tertentu pada firewall |
| `/fw deny <PORT>` | Menutup port tertentu pada firewall (OTP proteksi jika menutup port SSH) |
| `/fw rules` | Menampilkan list aturan firewall bernomor |

---

## 🔒 Model Keamanan Lapis Ganda (Dual-Layer Security Model)

### 1. Central OTP Confirmation Gate
Setiap tindakan kritis yang bersifat destruktif atau mengubah konfigurasi sistem dilindungi oleh **PIN OTP 4-digit dinamis** yang aman secara kriptografi:
- Memiliki waktu kedaluwarsa ketat selama **120 detik**.
- Admin dapat menyetujui langsung dengan membalas pesan obrolan menggunakan PIN angka saja atau mengetik `/confirm <OTP>`.

### 2. Safety Filter & Tokenized shlex
Setiap baris perintah shell yang dieksekusi oleh Executor disaring secara ketat melalui regex blacklist (`BLOCKED_PATTERNS_REGEX`) dan parsing token shlex untuk mencegah:
- Penghapusan jalur kritis seperti `rm -rf /` (termasuk deteksi bypass spasi ganda dan tanda kutip).
- Command injection dan chaining command menggunakan pipe `| sh` atau semicolon `;`.
- Eksekusi biner interpreter tersarang (`bash -c`, `sh -c`).

---

## 📂 Struktur Proyek

```
syamadmin/
├── install.sh                  # One-click installer sistem
├── config.env.example          # Template konfigurasi lingkungan
├── syamadmin.py                # Entry point utama daemon agen
├── syamadmin.service           # Unit file Systemd
├── USER_GUIDE.md               # Panduan lengkap operasional (ID/EN)
│
├── modules/
│   ├── telegram_bot.py         # Telegram Interface, Command & Wizard State Machine
│   ├── brain.py                # AI Decision Engine (Claude API + token usage tracker)
│   ├── provisioner.py          # LEMP Stack Installer & System Optimizer
│   ├── security.py             # SSH Harden, Fail2Ban, Audit, Threat Scanner & Port Tuner
│   ├── firewall.py             # Firewall UFW manager
│   ├── monitor.py              # System Monitor, auto alerts & autopilot diagnosis pemicu
│   ├── site_manager.py         # Nginx Virtual Host & Let's Encrypt SSL Manager
│   ├── backup.py               # Database & File backup engine
│   ├── notifier.py             # Notifikasi waspada Telegram
│   └── executor.py             # Safe Shell Executor dengan tokenized shlex & SQLite Audit Log
│
├── scripts/
│   ├── collect_trends.py       # Pengumpul tren metrik harian ke SQLite
│   ├── cron_job.py             # Task Runner aman untuk eksekusi berkala cron job
│   ├── setup_swap.sh           # Pembuat swap memori otomatis
│   └── ...
```

---

## 🗺 Roadmap

- [x] Scheduled task with cron expression support (via `/cron` NLP Scheduler)
- [x] Automated performance tuning recommendations (via `/optimize` Advisor)
- [x] Native tool-use AI routing (structured output, no fragile JSON parsing)
- [x] Multi-step AI orchestrator with live progress & halt-on-failure
- [x] Persistent Memory Core (preferences, chat history, incident lessons via FTS5)
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
