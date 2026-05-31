# Panduan Penggunaan SyamAdmin

**Versi:** 1.1  
**Terakhir diperbarui:** Mei 2026  
**Platform:** Ubuntu 22.04 LTS (VPS)

SyamAdmin adalah AI sysadmin agent yang mengelola server Ubuntu 22.04 secara otomatis melalui Telegram. Dari setup awal clean install hingga production-ready LEMP stack, monitoring real-time, security hardening, dan manajemen site — semua dikendalikan lewat chat Telegram dalam bahasa Indonesia maupun Inggris.

---

## Daftar Isi

1. [Prasyarat](#1-prasyarat)
2. [Instalasi](#2-instalasi)
3. [Konfigurasi](#3-konfigurasi)
4. [Menjalankan Agent](#4-menjalankan-agent)
5. [Referensi Cepat Perintah](#5-referensi-cepat-perintah)
6. [Perintah Telegram — Panduan Lengkap](#6-perintah-telegram--panduan-lengkap)
7. [Alur Kerja Umum](#7-alur-kerja-umum)
8. [Sistem Monitoring & Alert](#8-sistem-monitoring--alert)
9. [Keamanan & Hardening](#9-keamanan--hardening)
10. [Manajemen Site & SSL](#10-manajemen-site--ssl)
11. [Backup & Restore](#11-backup--restore)
12. [AI Brain — Perintah Natural Language](#12-ai-brain--perintah-natural-language)
13. [Struktur File & Direktori](#13-struktur-file--direktori)
14. [Troubleshooting](#14-troubleshooting)
15. [Keamanan Agent](#15-keamanan-agent)
16. [Glosarium](#16-glosarium)

---

## 1. Prasyarat

Sebelum menginstall SyamAdmin, pastikan Anda memiliki:

**Server:**

- VPS dengan Ubuntu 22.04 LTS (fresh install atau existing)
- Akses root (SSH)
- Minimal 1 GB RAM, 1 vCPU, 20 GB disk
- Koneksi internet aktif

**Akun & Token:**

- **Telegram Bot Token** — dibuat melalui [@BotFather](https://t.me/BotFather) di Telegram
- **Telegram User ID** — dapatkan dari [@userinfobot](https://t.me/userinfobot) atau [@RawDataBot](https://t.me/RawDataBot)
- **Anthropic API Key** *(opsional)* — dari [console.anthropic.com](https://console.anthropic.com) untuk fitur AI Brain

### Membuat Telegram Bot (Langkah demi Langkah)

Jika Anda belum pernah membuat bot Telegram:

1. Buka Telegram, ketuk ikon pencarian, cari **@BotFather**
2. Ketuk **Start** atau kirim `/start`
3. Kirim perintah `/newbot`
4. BotFather akan bertanya nama bot (contoh: `SyamAdmin Server`) — ketik nama yang Anda inginkan dan kirim
5. Selanjutnya BotFather meminta username (harus diakhiri `bot`, contoh: `syamvps_bot`) — ketik dan kirim
6. BotFather akan membalas dengan **token** berformat `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ` — **simpan token ini**, jangan bagikan ke siapa pun

**Mendapatkan User ID Anda:**

1. Cari **@userinfobot** di Telegram dan kirim pesan apa pun
2. Bot akan membalas dengan info Anda, termasuk angka **Id** (contoh: `987654321`)
3. Angka inilah yang diisi sebagai `TELEGRAM_ADMIN_ID` — bukan username Anda

---

## 2. Instalasi

### Instalasi Cepat (One-Click)

Upload file `syamadmin.tar.gz` ke server, lalu jalankan:

```bash
# Upload dari komputer lokal ke server
scp syamadmin.tar.gz root@IP_SERVER:~/

# SSH masuk ke server
ssh root@IP_SERVER

# Extract dan install
tar xzf syamadmin.tar.gz
cd syamadmin
chmod +x install.sh
sudo ./install.sh
```

Installer berjalan otomatis dan selesai dalam 1–3 menit. Anda akan melihat output berwarna yang menunjukkan progress setiap langkah.

### Apa yang Dilakukan Installer

Installer melakukan langkah-langkah berikut secara otomatis:

1. Memverifikasi OS (Ubuntu 22.04/24.04)
2. Menginstall system dependencies: `python3`, `python3-venv`, `curl`, `wget`, `git`, `sqlite3`, `htop`, `rkhunter`, `lynis`
3. Membuat direktori kerja:
   - `/opt/syamadmin/` — kode program
   - `/etc/syamadmin/` — konfigurasi
   - `/var/log/syamadmin/` — log file
   - `/var/lib/syamadmin/` — database SQLite
4. Membuat Python virtual environment di `/opt/syamadmin/venv/`
5. Menginstall Python packages: `python-telegram-bot`, `anthropic`, `psutil`, `aiosqlite`, dll.
6. Mendaftarkan systemd service `syamadmin` (agar jalan otomatis saat boot)
7. Mengkonfigurasi logrotate (rotasi log harian, retensi 14 hari)
8. Menginisialisasi database SQLite (tabel: `audit_log`, `metrics`, `sites`, `scheduled_tasks`, `alerts`)

---

## 3. Konfigurasi

Setelah instalasi, **wajib** edit file konfigurasi sebelum menjalankan agent:

```bash
sudo nano /etc/syamadmin/config.env
```

> **Tip untuk pemula:** `nano` adalah editor teks di terminal. Gunakan tombol panah untuk navigasi, `Ctrl+O` lalu Enter untuk menyimpan, `Ctrl+X` untuk keluar.

### Parameter Wajib

| Parameter | Contoh | Keterangan |
|-----------|--------|------------|
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdef...` | Token dari @BotFather |
| `TELEGRAM_ADMIN_ID` | `987654321` | Telegram User ID Anda (angka, bukan username) |

### Parameter Opsional (tapi Disarankan)

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `ANTHROPIC_API_KEY` | *(kosong)* | API key untuk fitur AI Brain. Tanpa ini, `/ai` menggunakan keyword parser sederhana |
| `SERVER_NAME` | `my-vps-01` | Nama identitas server (ditampilkan di notifikasi) |
| `SERVER_TIMEZONE` | `Asia/Makassar` | Timezone server |

### Parameter Monitoring (opsional)

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `ALERT_THRESHOLD_CPU` | `85` | Kirim alert jika CPU melebihi X% |
| `ALERT_THRESHOLD_RAM` | `90` | Kirim alert jika RAM melebihi X% |
| `ALERT_THRESHOLD_DISK` | `85` | Kirim alert jika disk melebihi X% |
| `ALERT_THRESHOLD_LOAD` | `4.0` | Kirim alert jika load average melebihi X |
| `MONITOR_INTERVAL` | `60` | Seberapa sering agent mengecek server (dalam detik) |

### Parameter Lainnya (opsional)

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `SSH_PORT` | `22` | Port SSH (digunakan oleh modul security & firewall) |
| `BACKUP_DIR` | `/var/backups/syamadmin` | Direktori penyimpanan backup |
| `BACKUP_RETENTION_DAYS` | `7` | Berapa hari backup disimpan sebelum dihapus otomatis |
| `PHP_VERSION` | `8.3` | Versi PHP yang diinstall oleh provisioner |
| `LOG_LEVEL` | `INFO` | Level logging: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Contoh Konfigurasi Minimal

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_ID=987654321
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
SERVER_NAME=vps-nustek-01
SERVER_TIMEZONE=Asia/Makassar
```

Setelah selesai mengedit, simpan file (`Ctrl+O`, Enter, `Ctrl+X`).

---

## 4. Menjalankan Agent

### Start, Stop, dan Restart

```bash
# Aktifkan agar jalan otomatis saat boot + jalankan sekarang
sudo systemctl enable --now syamadmin

# Cek status (apakah agent berjalan normal)
sudo systemctl status syamadmin

# Stop agent
sudo systemctl stop syamadmin

# Restart agent (diperlukan setelah edit config)
sudo systemctl restart syamadmin
```

### Memantau Log Agent

```bash
# Log real-time (tekan Ctrl+C untuk berhenti)
sudo journalctl -u syamadmin -f

# Atau langsung dari file log
sudo tail -f /var/log/syamadmin/agent.log
```

### Verifikasi Agent Berjalan

Setelah agent dijalankan, buka Telegram dan kirim `/start` ke bot Anda. Anda akan menerima pesan:

```
🤖 SyamAdmin Agent

Server: vps-nustek-01
Status: 🟢 Online

Kirim /help untuk daftar perintah.
```

Anda juga akan menerima notifikasi startup otomatis di Telegram:

```
🟢 SyamAdmin Agent Started
Server: vps-nustek-01
Status: Online & Ready
```

Jika tidak ada respons, cek bagian [Troubleshooting](#14-troubleshooting).

---

## 5. Referensi Cepat Perintah

Ini adalah daftar singkat semua perintah yang bisa Anda gunakan. Klik nama bagian untuk penjelasan lengkap.

### Monitoring & Informasi

| Perintah | Fungsi |
|----------|--------|
| `/status` | Dashboard server: CPU, RAM, disk, uptime |
| `/services` | Status semua managed services (nginx, mysql, dll.) |
| `/logs` | Log syslog terbaru (30 baris) |
| `/logs nginx` | Log error Nginx |
| `/logs mysql` | Log error MySQL |
| `/logs auth` | Log login SSH |
| `/logs fail2ban` | Log Fail2Ban (IP yang di-ban) |
| `/audit` | 15 perintah terakhir yang dieksekusi agent |

### Setup & Provisioning

| Perintah | Fungsi |
|----------|--------|
| `/provision` | Install Nginx + MySQL 8 + PHP 8.3 + Certbot (memerlukan konfirmasi) |
| `/confirm provision` | Konfirmasi dan mulai provisioning |

### Manajemen Site & SSL

| Perintah | Fungsi |
|----------|--------|
| `/site add example.com` | Buat vhost Nginx baru untuk domain |
| `/site add app.com laravel` | Buat vhost dengan konfigurasi Laravel |
| `/site list` | Tampilkan semua site yang dikelola |
| `/site ssl example.com` | Aktifkan HTTPS via Let's Encrypt |
| `/site remove example.com` | Hapus konfigurasi vhost (file web tetap ada) |

### Keamanan

| Perintah | Fungsi |
|----------|--------|
| `/security` | Audit keamanan komprehensif |
| `/harden` | Hardening SSH + Fail2Ban + UFW + auto-updates |

### Firewall (UFW)

| Perintah | Fungsi |
|----------|--------|
| `/firewall` | Tampilkan status UFW dan semua rule |
| `/fw allow 80` | Buka port 80 |
| `/fw deny 3306` | Blokir port 3306 |
| `/fw rules` | Tampilkan semua rule dengan nomor urut |

### Backup

| Perintah | Fungsi |
|----------|--------|
| `/backup` | Full backup: database + file web |
| `/backup db` | Backup semua database MySQL saja |
| `/backup files` | Backup file web + konfigurasi Nginx/PHP |
| `/backup list` | Tampilkan daftar backup yang tersedia |

### AI & Perintah Natural Language

| Perintah | Fungsi |
|----------|--------|
| `/ai [perintah bebas]` | Jalankan perintah dalam bahasa Indonesia/Inggris |
| *(teks bebas)* | Pesan tanpa `/` juga diproses AI secara otomatis |

### Utilitas

| Perintah | Fungsi |
|----------|--------|
| `/start` | Pesan selamat datang dan status agent |
| `/help` | Tampilkan ringkasan perintah |
| `/confirm [aksi]` | Konfirmasi aksi berbahaya (2 menit timeout) |

---

## 6. Perintah Telegram — Panduan Lengkap

### `/status` — Dashboard Server

Menampilkan snapshot kondisi server saat ini secara real-time.

**Cara pakai:**

```
/status
```

**Contoh output:**

```
🖥 Server Status — vps-nustek-01
⏱ Uptime: 14d 6h 32m

CPU [████░░░░░░] 38%
Cores: 2 | Load: 0.45/0.38/0.31

RAM [██████░░░░] 62%
Used: 1.2/2.0 GB

Disk [███░░░░░░░] 34%
Used: 6.8/20.0 GB

Network
↑ Sent: 4,521.3 MB | ↓ Recv: 12,845.7 MB
Processes: 127
```

**Penjelasan kolom:**

- **Load:** Angka beban rata-rata 1 menit / 5 menit / 15 menit. Umumnya aman jika di bawah jumlah CPU core.
- **Progress bar** `[████░░]`: Setiap blok ≈ 10%. Semakin penuh, semakin tinggi penggunaan.

---

### `/services` — Status Layanan

Mengecek apakah semua layanan yang dikelola SyamAdmin sedang berjalan.

**Cara pakai:**

```
/services
```

**Contoh output:**

```
🔧 Services Status

🟢 nginx — active (running)
🟢 mysql — active (running)
🟢 php8.3-fpm — active (running)
🟢 fail2ban — active (running)
🟢 ufw — active (running)
🟢 ssh — active (running)
```

Jika ada service yang berstatus 🔴 atau ⚫, gunakan AI untuk memperbaikinya:

```
/ai restart nginx
/ai cek kenapa mysql mati
```

---

### `/logs [service]` — Lihat Log

Menampilkan 30 baris terakhir dari file log yang diminta.

**Cara pakai:**

```
/logs             → log syslog (default)
/logs nginx       → error log Nginx
/logs mysql       → error log MySQL
/logs auth        → log login SSH
/logs fail2ban    → log Fail2Ban
```

**Contoh output `/logs nginx`:**

```
📋 Log: nginx

2026/05/31 08:12:01 [error] 1234#0: *5 connect() failed (111: Connection refused)
while connecting to upstream, client: 103.x.x.x, server: example.com
2026/05/31 08:12:45 [notice] 1234#0: signal process started
```

> **Tip:** Jika log sulit dibaca, gunakan `/ai analisis error log nginx` untuk mendapatkan penjelasan dari AI.

---

### `/audit` — Log Aktivitas Agent

Menampilkan 15 perintah terakhir yang dieksekusi oleh SyamAdmin, lengkap dengan timestamp dan status.

**Cara pakai:**

```
/audit
```

**Contoh output:**

```
📋 Recent Audit Log

✅ 2026-05-31 08:00:01 [monitor] systemctl status nginx
✅ 2026-05-31 08:01:15 [site_manager] certbot renew --quiet
❌ 2026-05-31 08:05:22 [executor] apt install redis — rc=1
✅ 2026-05-31 08:10:00 [backup] mysqldump --all-databases
```

---

### `/provision` — Setup LEMP Stack

Menginstall dan mengkonfigurasi seluruh komponen server web dari awal. Perintah ini memerlukan konfirmasi karena bersifat besar dan tidak bisa di-undo.

**Cara pakai:**

```
/provision
```

Agent akan meminta konfirmasi. Kirim:

```
/confirm provision
```

**Apa yang diinstall:**

| Komponen | Detail |
|----------|--------|
| **Nginx** | Web server, dikonfigurasi dengan gzip, security headers, worker tuning |
| **MySQL 8** | Database server, diamankan otomatis, password root digenerate (24 karakter acak) |
| **PHP 8.3** | Dengan 15 extensions: fpm, mysql, mbstring, xml, curl, gd, zip, intl, bcmath, redis, opcache, dll. |
| **Composer** | Dependency manager untuk PHP (dibutuhkan Laravel, dll.) |
| **Certbot** | Tool untuk SSL gratis dari Let's Encrypt |
| **Swap 2 GB** | Virtual memory tambahan (hanya jika belum ada) |

**Contoh output selama proses:**

```
🚀 Memulai instalasi LEMP stack...

📦 [1/7] Updating system packages... ✅
🌐 [2/7] Installing Nginx... ✅
🗄  [3/7] Installing MySQL 8... ✅
🐘 [4/7] Installing PHP 8.3 + extensions... ✅
🎼 [5/7] Installing Composer... ✅
🔒 [6/7] Installing Certbot... ✅
💾 [7/7] Configuring swap... ✅

✅ LEMP Stack Installation Complete!
⏱ Duration: 7m 32s

🔑 MySQL root password: xK7#mPq9vRs2
   (Disimpan di /root/.my.cnf)
```

> **Penting:** Catat password MySQL root di tempat yang aman (password manager, catatan terenkripsi). Password ini juga tersimpan di `/root/.my.cnf` dan `/etc/syamadmin/config.env`.

**Proses memakan waktu 5–10 menit** tergantung kecepatan server dan koneksi internet.

---

### `/site` — Manajemen Situs Web

#### Tambah Site Baru

```
/site add example.com
/site add app.com laravel
```

**Apa yang terjadi:**

1. Membuat direktori: `/var/www/example.com/public_html/`
2. Membuat halaman `index.html` default
3. Membuat konfigurasi Nginx (dengan PHP-FPM, security headers, clean URL)
4. Membuat PHP-FPM pool terisolasi untuk site ini
5. Mengaktifkan site dan reload Nginx
6. Menyimpan data ke database

Untuk **Laravel**, document root otomatis diarahkan ke folder `public/` dan `try_files` dikonfigurasi untuk routing Laravel.

**Contoh output:**

```
✅ Site example.com berhasil ditambahkan!

📁 Document root: /var/www/example.com/public_html/
🔧 PHP-FPM pool: example.com
⚙️ Config: /etc/nginx/sites-enabled/example.com

Upload file Anda ke folder di atas.
Aktifkan SSL: /site ssl example.com
```

#### Aktifkan SSL (HTTPS)

```
/site ssl example.com
```

> **Prasyarat:** DNS A record domain harus sudah mengarah ke IP server ini. Cek dengan: `dig +short example.com` — harus menampilkan IP server Anda.

**Contoh output:**

```
🔒 Setting up SSL for example.com...

✅ Certificate issued successfully!
✅ HTTP → HTTPS redirect aktif
✅ Auto-renewal dikonfigurasi
✅ HSTS header ditambahkan

🌐 Site Anda sekarang bisa diakses di: https://example.com
```

#### List Semua Site

```
/site list
```

**Contoh output:**

```
🌐 Managed Sites (3)

1. example.com
   📁 /var/www/example.com/public_html/
   🔒 SSL: aktif
   
2. app.mycompany.com
   📁 /var/www/app.mycompany.com/public/
   🔒 SSL: aktif
   🏗️ Framework: laravel

3. dev.example.com
   📁 /var/www/dev.example.com/public_html/
   🔓 SSL: belum aktif
```

#### Hapus Site

```
/site remove example.com
```

> **Catatan:** Konfigurasi Nginx dihapus dan site dinonaktifkan, tapi **file di `/var/www/example.com/` tidak dihapus** untuk keamanan. Hapus manual jika memang tidak diperlukan.

---

### `/security` — Audit Keamanan

Menjalankan pemeriksaan keamanan menyeluruh dan melaporkan hasilnya.

**Cara pakai:**

```
/security
```

**Apa yang diperiksa:**

| Pemeriksaan | Keterangan |
|-------------|------------|
| SSH password auth | Apakah login dengan password masih diizinkan? |
| SSH root login | Apakah root bisa login langsung? |
| Fail2Ban status | Aktif atau tidak, berapa IP yang di-ban |
| UFW firewall | Aktif atau tidak |
| Unattended upgrades | Auto security update sudah disetup? |
| Open ports | Port apa saja yang sedang mendengarkan |
| Package updates | Berapa paket yang tersedia untuk diupdate |
| Login history | 5 login terakhir ke server |

**Contoh output:**

```
🔍 Security Audit — vps-nustek-01

SSH:
  ⚠️  Password auth: ENABLED (sebaiknya dimatikan)
  ✅ Root login: prohibit-password

Fail2Ban:
  ✅ Status: active
  📊 Banned IPs: 12 (SSH: 8, Nginx: 4)

Firewall:
  ✅ UFW: active
  🔓 Open ports: 22, 80, 443

Updates:
  📦 Tersedia: 7 package updates (3 security)

Login History:
  2026-05-31 08:00 root dari 103.x.x.x
  2026-05-30 14:22 root dari 103.x.x.x

💡 Saran: Jalankan /harden untuk memperbaiki masalah di atas.
```

---

### `/harden` — Hardening Keamanan

Menjalankan semua proses penguatan keamanan dalam satu perintah.

**Cara pakai:**

```
/harden
```

> ⚠️ **Peringatan penting:** `/harden` akan mematikan login SSH dengan password. Pastikan Anda sudah menambahkan SSH public key ke server sebelum menjalankan perintah ini. Jika tidak, Anda bisa terkunci dari server sendiri.
>
> Cara menambahkan SSH key (dari komputer lokal Anda):
>
> ```bash
> ssh-copy-id root@IP_SERVER
> ```

**Empat proses yang dijalankan:**

**1. SSH Hardening**

- Mematikan login dengan password (hanya SSH key)
- Root login hanya via key
- Maksimal 3 percobaan login salah
- Sesi idle otomatis terputus setelah 5 menit

**2. Fail2Ban Setup**

- SSH brute force: 3 percobaan salah → ban 2 jam
- Nginx HTTP auth attack: 3 percobaan → ban 1 jam
- Nginx bot scanner: aktif
- Nginx rate limit: aktif

**3. Firewall Defaults**

- Policy default: tolak semua incoming, izinkan semua outgoing
- Port yang dibuka: SSH (22), HTTP (80), HTTPS (443)

**4. Auto Security Updates**

- Install dan aktifkan `unattended-upgrades` (update keamanan otomatis)

**Contoh output:**

```
🔐 Hardening Complete!

SSH: ✅ Password auth dimatikan, key-only aktif
Fail2Ban: ✅ Jails aktif (SSH, Nginx)
Firewall: ✅ Default deny, port 22/80/443 terbuka
Auto-updates: ✅ Unattended-upgrades aktif
```

---

### `/firewall` dan `/fw` — Manajemen Firewall

#### Lihat Status Firewall

```
/firewall
```

**Contoh output:**

```
🛡️ UFW Firewall Status: active

Default: deny (incoming) | allow (outgoing)

Rules:
22/tcp     ALLOW     Anywhere
80/tcp     ALLOW     Anywhere
443/tcp    ALLOW     Anywhere
3306/tcp   DENY      Anywhere
```

#### Operasi Firewall Cepat

```
/fw allow 3306    → Buka port 3306 (MySQL)
/fw allow 6379    → Buka port 6379 (Redis)
/fw allow 8080    → Buka port 8080 (web alternatif)
/fw deny 3306     → Tutup port 3306
/fw rules         → Tampilkan semua rule dengan nomor
```

**Contoh output `/fw allow 3306`:**

```
✅ Port 3306 dibuka (TCP)
Rule ditambahkan: 3306/tcp ALLOW Anywhere
```

> **Tip:** Buka port hanya yang benar-benar dibutuhkan. Semakin sedikit port terbuka, semakin aman server Anda.

---

### `/backup` — Backup Data

#### Full Backup

```
/backup
```

Menjalankan backup database dan file sekaligus.

**Contoh output:**

```
💾 Starting full backup...

🗄  Database backup...
    ✅ all_databases_20260531_020000.sql.gz (24.3 MB)

📁 File backup...
    ✅ webfiles_20260531_020030.tar.gz (158.7 MB)

✅ Full backup selesai!
📁 Lokasi: /var/backups/syamadmin/
🗑️  Backup > 7 hari dihapus otomatis.
```

#### Backup Database Saja

```
/backup db
```

Hanya backup database MySQL (lebih cepat).

#### Backup File Saja

```
/backup files
```

Backup file web (`/var/www/`) dan konfigurasi (`/etc/nginx/`, `/etc/php/`).

#### Lihat Daftar Backup

```
/backup list
```

**Contoh output:**

```
💾 Available Backups

Database Backups:
  all_databases_20260531_020000.sql.gz — 24.3 MB — 2026-05-31 02:00
  all_databases_20260530_020000.sql.gz — 23.8 MB — 2026-05-30 02:00
  all_databases_20260529_020000.sql.gz — 23.1 MB — 2026-05-29 02:00

File Backups:
  webfiles_20260531_020030.tar.gz — 158.7 MB — 2026-05-31 02:00
  webfiles_20260530_020030.tar.gz — 155.2 MB — 2026-05-30 02:00

Total: 5 backups | 385.1 MB
```

---

### `/ai` — Perintah Natural Language

Gunakan `/ai` untuk memberi perintah dalam bahasa bebas — Indonesia atau Inggris.

**Format:**

```
/ai [perintah dalam bahasa bebas]
```

**Contoh penggunaan:**

```
/ai restart nginx
/ai cek kenapa disk penuh
/ai tambah site portal.desa.id dengan laravel
/ai install redis-server
/ai buka port 6379 di firewall
/ai backup database sekarang
/ai scan rootkit
/ai update semua package
/ai lihat siapa saja yang login hari ini
/ai analisis error log nginx
/ai berapa banyak koneksi MySQL aktif
/ai restart semua service yang down
```

Pesan teks bebas (tanpa awalan `/`) juga otomatis dikirim ke AI Brain — Anda tidak harus selalu mengetik `/ai` di awal.

> Lihat bagian [AI Brain](#12-ai-brain--perintah-natural-language) untuk penjelasan lebih lengkap.

---

### `/confirm` — Konfirmasi Aksi Berbahaya

Beberapa aksi memerlukan konfirmasi eksplisit sebelum dieksekusi. Konfirmasi berlaku selama **2 menit** — lewat dari itu, aksi dibatalkan otomatis.

```
/confirm provision    → konfirmasi instalasi LEMP
/confirm ai          → konfirmasi perintah AI berisiko
```

Alternatif: balas dengan `ya`, `yes`, `ok`, `lanjut`, atau `confirm` sebagai teks bebas.

---

## 7. Alur Kerja Umum

### Skenario A: Setup Server Baru dari Nol

Ini adalah alur yang disarankan untuk server baru:

```
Langkah 1 — Verifikasi koneksi
/start
→ Bot menyapa dan menampilkan status online

Langkah 2 — Install LEMP stack
/provision
→ Bot meminta konfirmasi
/confirm provision
→ Progress instalasi 5–10 menit
→ Catat password MySQL root yang diberikan!

Langkah 3 — Hardening keamanan
(Pastikan SSH key sudah terpasang dulu!)
/harden
→ SSH, Fail2Ban, UFW, auto-updates dikonfigurasi

Langkah 4 — Verifikasi semuanya berjalan
/status
/services
/security

Langkah 5 — Tambah site pertama
/site add example.com
→ Upload file ke /var/www/example.com/public_html/
/site ssl example.com
→ HTTPS aktif
```

---

### Skenario B: Menambah Site Baru

```
/site add toko.example.com
→ ✅ Site dibuat

/site ssl toko.example.com
→ ✅ HTTPS aktif

→ Upload file ke /var/www/toko.example.com/public_html/
```

Untuk Laravel:

```
/site add app.com laravel
→ ✅ Site dibuat, document root di /var/www/app.com/public/
→ Upload project Laravel ke /var/www/app.com/

/site ssl app.com
→ ✅ HTTPS aktif
```

---

### Skenario C: Menangani Disk Penuh

```
Bot mengirim alert otomatis:
→ 🔴 Alert CRITICAL: Disk hampir penuh: 92% (18.4/20.0 GB)

Anda:
/ai cek folder apa yang paling banyak menggunakan disk

Bot:
→ Menjalankan analisis dan melaporkan:
   /var/log: 4.2 GB
   /var/www: 8.1 GB
   /var/backups: 5.9 GB

Anda:
/ai hapus log lama di /var/log yang lebih dari 30 hari

Bot:
→ ⚠️ Konfirmasi diperlukan. Kirim 'ya' untuk melanjutkan.

Anda:
ya

Bot:
→ ✅ Log lama dibersihkan. Disk turun ke 61%.
```

---

### Skenario D: Monitoring Harian

Anda tidak perlu melakukan apa pun secara aktif. Agent akan:

- Mengecek CPU, RAM, disk, load setiap 60 detik
- Mengecek status semua managed services
- Mengirim alert otomatis jika ada yang melewati batas

Jika ingin cek manual kapan saja:

```
/status      → ringkasan kondisi server
/services    → status per service
/logs nginx  → error log terbaru Nginx
```

---

### Skenario E: Respons Insiden — Service Down

```
Bot mengirim alert otomatis:
→ 🔴 Alert CRITICAL: Service nginx DOWN

Anda:
/ai restart nginx

Bot:
→ ✅ nginx di-restart. Status: active (running).

(Jika masih bermasalah)
/ai analisis kenapa nginx gagal start

Bot:
→ Menganalisis log dan melaporkan penyebab.
```

---

## 8. Sistem Monitoring & Alert

### Cara Kerja Monitoring

Agent menjalankan background loop yang mengumpulkan metrik sistem setiap `MONITOR_INTERVAL` detik (default: 60). Metrik disimpan ke database SQLite untuk analisis tren.

### Threshold Alert

| Metrik | Default | Pesan Alert |
|--------|---------|-------------|
| CPU > 85% | `ALERT_THRESHOLD_CPU` | Tampilkan top processes penyebab |
| RAM > 90% | `ALERT_THRESHOLD_RAM` | Tampilkan used/total |
| Disk > 85% | `ALERT_THRESHOLD_DISK` | ⚠️ **CRITICAL** — segera tindak |
| Load > 4.0 | `ALERT_THRESHOLD_LOAD` | Tampilkan load average |
| Service down | — | ⚠️ **CRITICAL** — saran restart |

**Contoh alert yang Anda terima di Telegram:**

```
🔴 Alert — CRITICAL
Server: vps-nustek-01
Module: monitor

Disk hampir penuh: 92% (18.4/20.0 GB)

Saran: Bersihkan /var/log atau perluas storage.
```

### Alert Cooldown

Untuk menghindari spam notifikasi, alert yang sama tidak akan dikirim ulang dalam **5 menit**. Jika CPU tetap tinggi selama 10 menit, Anda menerima 2 alert (bukan 10).

### Service Monitoring

Setiap loop, agent mengecek apakah managed services masih running. Jika ada yang down, alert dikirim dengan saran perintah restart.

Services yang dipantau: `nginx`, `mysql`, `php8.3-fpm`, `fail2ban`, `ufw`, `ssh`

---

## 9. Keamanan & Hardening

### Lapisan Keamanan Setelah `/harden`

**SSH:**

- Password authentication dimatikan (hanya SSH key)
- Root login hanya via key (`prohibit-password`)
- Maksimal 3 percobaan login salah
- Sesi idle disconnect setelah 5 menit (ClientAliveInterval 300s)
- X11 forwarding, agent forwarding, TCP forwarding: dimatikan

**Fail2Ban:**

- SSH brute force: 3 attempts → ban 2 jam
- Nginx HTTP auth: 3 attempts → ban 1 jam
- Nginx bot search detection: aktif
- Nginx rate limit enforcement: aktif

**Firewall (UFW):**

- Policy default: deny semua incoming, allow semua outgoing
- Hanya SSH, HTTP (80), HTTPS (443) yang dibuka

**Nginx:**

- `server_tokens off` — versi Nginx tidak ditampilkan
- Security headers: X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy
- File sensitif (`.env`, `.git`, `.htaccess`) di-deny
- Dengan SSL: HSTS, TLS 1.2/1.3 only, cipher suite modern

**PHP:**

- Header `X-Powered-By` disembunyikan

### Rutinitas Keamanan yang Disarankan

| Frekuensi | Tindakan |
|-----------|----------|
| Mingguan | `/security` — cek audit |
| Mingguan | `/backup` — full backup manual |
| Bulanan | Review log auth: `/logs auth` |
| Saat ada update | `/ai update semua package` |

---

## 10. Manajemen Site & SSL

### Struktur Direktori Site

```
/var/www/example.com/
└── public_html/          ← document root (default)
    └── index.html        ← halaman default yang dibuat agent

# Untuk framework Laravel:
/var/www/myapp.com/
├── public/               ← document root (dikonfigurasi agent)
│   └── index.php
├── app/
├── config/
└── ...
```

Upload file aplikasi Anda ke folder `public_html/` (atau `public/` untuk Laravel).

### Konfigurasi Nginx yang Digenerate Otomatis

Setiap vhost sudah dikonfigurasi dengan:

- PHP-FPM via Unix socket (performa lebih baik dari TCP)
- Security headers
- Static asset caching: 30 hari untuk images, CSS, JS, fonts
- Hidden file denial: `.env`, `.git`, `.htaccess`
- Clean URL (`try_files`) — kompatibel dengan Laravel, WordPress, CodeIgniter, dan framework PHP lainnya

### SSL Certificate (HTTPS)

SSL menggunakan **Let's Encrypt** (gratis) via Certbot:

- Redirect otomatis dari HTTP ke HTTPS
- TLS 1.2 dan 1.3
- HSTS header (max-age 2 tahun)
- OCSP stapling
- Auto-renewal via certbot timer (tidak perlu perpanjang manual)

**Prasyarat SSL:**

1. Domain harus sudah mengarah ke IP server: `dig +short example.com` → tampil IP server
2. Port 80 harus terbuka: `/fw allow 80`
3. Let's Encrypt rate limit: maksimal 5 sertifikat per domain per minggu

---

## 11. Backup & Restore

### Lokasi Backup

```
/var/backups/syamadmin/
├── db/
│   └── all_databases_20260531_020000.sql.gz    ← backup database
└── files/
    └── webfiles_20260531_020030.tar.gz          ← backup file web
```

### Yang Dibackup

**Database backup (`/backup db`):**

- Semua database MySQL dengan `mysqldump --all-databases`
- `--single-transaction`: konsisten tanpa lock (cocok untuk database yang sedang aktif)
- `--routines --triggers`: termasuk stored procedures dan triggers
- Output dikompresi gzip

**File backup (`/backup files`):**

- `/var/www/` — semua file web
- `/etc/nginx/` — konfigurasi Nginx
- `/etc/php/` — konfigurasi PHP

### Restore Manual

Jika perlu restore dari backup:

**Restore database:**

```bash
gunzip < /var/backups/syamadmin/db/all_databases_20260531_020000.sql.gz | mysql -u root
```

**Restore file:**

```bash
tar xzf /var/backups/syamadmin/files/webfiles_20260531_020030.tar.gz -C /
```

### Retensi Otomatis

Backup yang lebih lama dari `BACKUP_RETENTION_DAYS` (default: 7 hari) dihapus otomatis setiap kali full backup dijalankan. Ubah nilai ini di `config.env` jika ingin menyimpan lebih lama.

---

## 12. AI Brain — Perintah Natural Language

### Cara Kerja

Ketika Anda mengirim `/ai [perintah]`, prosesnya:

```
Anda kirim:  /ai cek kenapa disk penuh
                ↓
Agent kumpulkan konteks server (CPU, RAM, disk, uptime)
                ↓
Claude API menganalisis intent + konteks
                ↓
Claude menentukan: modul=monitor, aksi=disk_usage
                ↓
Agent menjalankan analisis disk
                ↓
Hasil dilaporkan ke Telegram
```

### Contoh Perintah AI

**Monitoring & Diagnostik:**

```
/ai cek status server
/ai lihat proses apa yang paling banyak makan CPU
/ai berapa banyak koneksi aktif ke MySQL
/ai cek kenapa server lambat
/ai lihat siapa saja yang login hari ini
/ai analisis error log nginx
/ai cek disk usage per folder
```

**Manajemen Service:**

```
/ai restart nginx
/ai restart mysql
/ai restart php-fpm
/ai restart semua service yang down
/ai cek kenapa nginx gagal start
```

**Instalasi & Update:**

```
/ai install redis-server
/ai install nodejs
/ai update semua package keamanan
/ai install composer
```

**Keamanan:**

```
/ai scan rootkit
/ai lihat IP yang di-ban fail2ban
/ai cek port apa saja yang terbuka
/ai unban IP 103.x.x.x dari fail2ban
```

**Firewall:**

```
/ai buka port 6379 untuk Redis
/ai tutup port 3306 dari luar
/ai lihat semua rule firewall
```

**Site & Database:**

```
/ai tambah site portal.desa.id dengan laravel
/ai aktifkan SSL untuk portal.desa.id
/ai backup database sekarang
/ai lihat daftar database yang ada
```

**Pembersihan:**

```
/ai hapus log lama lebih dari 30 hari
/ai bersihkan cache apt
/ai lihat file besar di server
```

### Konfirmasi Perintah Berisiko

Jika AI mendeteksi perintah yang berisiko (menghapus data, mengubah konfigurasi kritis, menjalankan shell command langsung), agent akan meminta konfirmasi:

```
Anda: /ai hapus semua backup lama

Bot:  ⚠️ Konfirmasi Diperlukan

      Intent: Menghapus semua backup lebih dari 7 hari
      Aksi: backup.cleanup
      
      Ini akan menghapus permanen data backup. Lanjutkan?
      
      Kirim 'ya' atau /confirm ai dalam 2 menit.

Anda: ya

Bot:  ✅ 12 backup lama dihapus. Disk tersisa: 8.2 GB.
```

### Fallback Mode (tanpa API Key)

Jika `ANTHROPIC_API_KEY` tidak diset, AI Brain menggunakan keyword parser sederhana. Perintah dasar berikut masih dikenali:

| Kata kunci | Aksi |
|------------|------|
| `status`, `kesehatan` | Tampilkan status server |
| `service`, `layanan` | Cek status services |
| `provision`, `lemp` | Install LEMP stack |
| `firewall`, `ufw` | Status firewall |
| `security`, `audit` | Security audit |
| `backup` | Full backup |
| `restart nginx/mysql/php` | Restart service |
| `disk`, `storage` | Cek disk usage |

Untuk kemampuan penuh (perintah kompleks, pemahaman konteks, bahasa bebas), pasang `ANTHROPIC_API_KEY` di konfigurasi.

---

## 13. Struktur File & Direktori

### File Program (di Server)

```
/opt/syamadmin/
├── syamadmin.py             # Entry point daemon
├── venv/                    # Python virtual environment
├── modules/
│   ├── brain.py             # AI decision engine (Claude API)
│   ├── telegram_bot.py      # Telegram interface & command handlers
│   ├── provisioner.py       # LEMP stack installer & optimizer
│   ├── security.py          # Hardening, audit, rootkit scan
│   ├── firewall.py          # UFW rule management
│   ├── monitor.py           # Metrics loop & threshold alerts
│   ├── site_manager.py      # Nginx vhost, PHP-FPM, SSL
│   ├── backup.py            # MySQL dump & file backup engine
│   ├── notifier.py          # Telegram notification sender
│   └── executor.py          # Safe shell executor + audit logger
├── templates/
│   ├── nginx_vhost.conf     # Template Nginx vhost HTTP
│   ├── nginx_ssl.conf       # Template Nginx vhost HTTPS
│   └── php_fpm_pool.conf    # Template PHP-FPM pool per site
└── scripts/
    ├── harden_ssh.sh        # Script hardening SSH
    ├── setup_fail2ban.sh    # Script setup Fail2Ban
    └── setup_swap.sh        # Script setup swap file
```

### File Konfigurasi & Data

```
/etc/syamadmin/config.env         # Konfigurasi (hanya root yang bisa baca)
/var/log/syamadmin/agent.log      # Log agent
/var/lib/syamadmin/syamadmin.db   # Database SQLite (audit, metrics, sites)
/var/backups/syamadmin/           # Direktori backup
```

### Systemd Service

```
/etc/systemd/system/syamadmin.service
```

---

## 14. Troubleshooting

### Agent Tidak Merespons di Telegram

**Langkah 1:** Cek apakah service berjalan

```bash
sudo systemctl status syamadmin
```

Jika status `inactive` atau `failed`, lanjut ke langkah 2.

**Langkah 2:** Lihat log error

```bash
sudo journalctl -u syamadmin -n 50
```

Cari baris yang mengandung `ERROR` atau `CRITICAL`.

**Langkah 3:** Restart agent

```bash
sudo systemctl restart syamadmin
```

**Langkah 4:** Jika masih tidak jalan, debug manual

```bash
sudo systemctl stop syamadmin
sudo /opt/syamadmin/venv/bin/python3 /opt/syamadmin/syamadmin.py
```

Error akan langsung terlihat di terminal.

**Hal yang perlu dicek:**

- `TELEGRAM_BOT_TOKEN` benar? (token berformat angka:huruf panjang)
- `TELEGRAM_ADMIN_ID` benar? (angka, bukan username)
- Server bisa akses internet? (`ping 8.8.8.8`)

---

### "Unauthorized" Saat Kirim Perintah

Hanya user dengan `TELEGRAM_ADMIN_ID` yang cocok yang bisa menggunakan bot.

Verifikasi User ID Anda:

1. Buka [@userinfobot](https://t.me/userinfobot) di Telegram
2. Kirim pesan apa pun
3. Catat angka di field **Id**
4. Pastikan angka ini sama persis dengan `TELEGRAM_ADMIN_ID` di config

---

### Provision Gagal di Tengah Jalan

**Cek log:**

```bash
sudo tail -100 /var/log/syamadmin/agent.log
```

**Perbaiki dpkg jika macet:**

```bash
sudo rm -f /var/lib/dpkg/lock-frontend
sudo dpkg --configure -a
```

**Jalankan ulang `/provision`** — komponen yang sudah terinstall akan di-skip otomatis.

---

### SSL Gagal

Penyebab paling umum dan solusinya:

| Penyebab | Cara Cek | Solusi |
|----------|----------|--------|
| DNS belum propagasi | `dig +short example.com` → harus tampil IP server | Tunggu 5–60 menit, coba lagi |
| Port 80 diblokir | Cek dari luar: `curl http://example.com` | `/fw allow 80` |
| Rate limit Let's Encrypt | Error: "too many certificates" | Tunggu 1 minggu |
| Domain salah ketik | Cek dengan `/site list` | Hapus dan buat ulang |

---

### AI Brain Error / Tidak Merespons

- Pastikan `ANTHROPIC_API_KEY` valid dan ada kredit di akun Anthropic
- Cek log: `sudo tail -50 /var/log/syamadmin/agent.log`
- AI Brain otomatis fallback ke keyword parser jika API gagal — perintah dasar tetap bisa digunakan

---

### Agent Crash Loop (Restart Terus)

```bash
# Cek log detail
sudo journalctl -u syamadmin -n 100 --no-pager

# Stop sementara
sudo systemctl stop syamadmin

# Debug manual — error langsung terlihat
sudo /opt/syamadmin/venv/bin/python3 /opt/syamadmin/syamadmin.py
```

---

### Database SQLite Corrupt

```bash
# Backup dulu
cp /var/lib/syamadmin/syamadmin.db /var/lib/syamadmin/syamadmin.db.bak

# Cek integrity
sqlite3 /var/lib/syamadmin/syamadmin.db "PRAGMA integrity_check;"
```

Jika corrupt, buat database baru (data historis hilang, tapi agent tetap berjalan normal):

```bash
rm /var/lib/syamadmin/syamadmin.db
sudo systemctl restart syamadmin
```

---

### Terkunci dari Server (SSH Tidak Bisa Masuk)

Jika Anda menjalankan `/harden` tanpa SSH key terpasang dan sekarang tidak bisa SSH:

1. Login via **console VPS** (panel kontrol provider Anda biasanya ada fitur "VPS Console" atau "KVM")
2. Edit config SSH: `sudo nano /etc/ssh/sshd_config`
3. Ubah `PasswordAuthentication no` → `PasswordAuthentication yes`
4. Restart SSH: `sudo systemctl restart sshd`
5. SSH masuk, tambahkan SSH key, lalu `/harden` lagi

---

## 15. Keamanan Agent

### Command Safety Filter

Setiap shell command yang dieksekusi SyamAdmin melewati safety filter. Perintah berikut **diblokir secara permanen** — tidak bisa dieksekusi melalui cara apapun, bahkan via `/ai`:

| Perintah | Alasan Diblokir |
|----------|-----------------|
| `rm -rf /` | Menghapus seluruh filesystem |
| `mkfs.*` | Memformat disk |
| `> /dev/sda` | Menulis langsung ke raw disk |
| `:(){:\|:&};:` | Fork bomb — crash sistem |
| `chmod -R 777 /` | Membuka semua permission |
| `curl \| bash` | Eksekusi kode dari internet tanpa verifikasi |

### Audit Trail

Setiap perintah yang dieksekusi agent dicatat di database dengan:

- Timestamp
- Modul pemanggil
- Perintah yang dijalankan (dibatasi 200 karakter)
- Durasi eksekusi
- User ID Telegram
- Status: success / failed / blocked / timeout

Lihat via `/audit` di Telegram, atau query langsung:

```bash
sqlite3 /var/lib/syamadmin/syamadmin.db \
  "SELECT timestamp, module, action, status FROM audit_log ORDER BY id DESC LIMIT 20;"
```

### Access Control

- Hanya satu admin (berdasarkan `TELEGRAM_ADMIN_ID`) yang bisa mengontrol bot
- Percobaan akses dari user lain dicatat sebagai security event
- Operasi berbahaya memerlukan konfirmasi eksplisit dengan timeout 2 menit
- File konfigurasi: permission `600` (hanya root yang bisa membaca)

---

## 16. Glosarium

Istilah teknis yang sering muncul dalam panduan ini:

| Istilah | Penjelasan |
|---------|------------|
| **VPS** | Virtual Private Server — server virtual yang Anda sewa dari provider cloud |
| **LEMP** | Linux + Nginx + MySQL + PHP — paket software standar untuk web hosting |
| **SSH** | Secure Shell — protokol untuk login ke server secara aman dari terminal |
| **SSH key** | Sepasang kunci kriptografi (publik + privat) sebagai pengganti password SSH |
| **Nginx** | Web server — menerima request dari pengunjung dan meneruskan ke PHP |
| **PHP-FPM** | PHP FastCGI Process Manager — menjalankan kode PHP untuk tiap site |
| **MySQL** | Database server — menyimpan data aplikasi web |
| **UFW** | Uncomplicated Firewall — tool untuk mengatur aturan koneksi masuk/keluar |
| **Fail2Ban** | Tool yang memblokir IP yang terlalu sering gagal login (brute force) |
| **SSL/TLS** | Protokol enkripsi untuk HTTPS — membuat koneksi aman antara browser dan server |
| **Let's Encrypt** | Layanan sertifikat SSL gratis yang digunakan SyamAdmin |
| **Certbot** | Tool yang mengurus pembuatan dan pembaruan sertifikat Let's Encrypt |
| **systemd** | Sistem manajemen service di Linux — mengurus start/stop/restart program |
| **Audit log** | Catatan semua aktivitas yang dilakukan oleh agent |
| **SQLite** | Database ringan berbasis file — digunakan SyamAdmin untuk menyimpan data |
| **vhost** | Virtual host — konfigurasi Nginx untuk satu domain tertentu |
| **Document root** | Folder yang berisi file web yang bisa diakses pengunjung |
| **Port** | Angka yang menentukan jenis koneksi jaringan (80=HTTP, 443=HTTPS, 22=SSH) |
| **Load average** | Ukuran beban rata-rata server dalam 1, 5, dan 15 menit terakhir |
| **Composer** | Tool manajemen paket untuk PHP — seperti `npm` untuk Node.js |
| **AI Brain** | Modul SyamAdmin yang menggunakan Claude API untuk memahami perintah bebas |

---

*SyamAdmin — dibuat oleh @syams_ideris untuk menyederhanakan hidup sysadmin.*  
*Made in Banjarmasin - South Kalimantan 🇮🇩*
