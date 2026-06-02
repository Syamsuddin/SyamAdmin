# Panduan Penggunaan SyamAdmin

**Versi:** 3.2
**Terakhir diperbarui:** Juni 2026
**Platform:** Ubuntu 22.04 LTS (VPS)

SyamAdmin adalah **AI sysadmin agent** yang mengelola server Ubuntu sepenuhnya melalui Telegram. Di balik layar ada **Jarwo** — persona AI sysadmin senior yang ramah, bisa diajak ngobrol bahasa Indonesia maupun Inggris, mengingat preferensi Anda, dan proaktif memberi saran. Dari clean install hingga LEMP stack production-ready, monitoring real-time, hardening keamanan, manajemen site & SSL, backup otomatis, sampai **firewall pre-emptive berbasis AI (PeFi)** yang memblokir serangan sebelum berhasil — semua dikendalikan lewat chat.

> **Apa yang baru di v3.2:** firewall pre-emptive `/pefi`, self-update dari GitHub `/update`, profil admin & persona Jarwo `/profile`, ganti model AI `/model`, penjadwalan natural language `/cron`, analisis optimasi `/optimize`, kontrol layanan langsung `/service`, dan Memory Core 4-pilar (server-state, preferensi, riwayat chat, pelajaran insiden).

---

## Daftar Isi

1. [Prasyarat](#1-prasyarat)
2. [Instalasi](#2-instalasi)
3. [Konfigurasi](#3-konfigurasi)
4. [Menjalankan Agent](#4-menjalankan-agent)
5. [Referensi Cepat Perintah](#5-referensi-cepat-perintah)
6. [Perintah Telegram — Panduan Lengkap](#6-perintah-telegram--panduan-lengkap)
7. [PeFi — Pre-Emptive Firewall Agent](#7-pefi--pre-emptive-firewall-agent)
8. [AI Brain & Jarwo — Natural Language](#8-ai-brain--jarwo--natural-language)
9. [Memory Core — Personalisasi Agen](#9-memory-core--personalisasi-agen)
10. [Alur Kerja Umum](#10-alur-kerja-umum)
11. [Monitoring & Alert](#11-monitoring--alert)
12. [Keamanan & Hardening](#12-keamanan--hardening)
13. [Manajemen Site & SSL](#13-manajemen-site--ssl)
14. [Backup & Restore](#14-backup--restore)
15. [Self-Update & Update OS](#15-self-update--update-os)
16. [Sistem Konfirmasi OTP](#16-sistem-konfirmasi-otp)
17. [Struktur File & Direktori](#17-struktur-file--direktori)
18. [Troubleshooting](#18-troubleshooting)
19. [Keamanan Agent](#19-keamanan-agent)
20. [Glosarium](#20-glosarium)

---

## 1. Prasyarat

**Server:**

- VPS dengan Ubuntu 22.04 LTS (fresh install atau existing). Ubuntu 24.04 juga didukung.
- Akses root (SSH)
- Minimal 1 GB RAM, 1 vCPU, 20 GB disk
- Koneksi internet aktif

**Akun & Token:**

- **Telegram Bot Token** — dibuat melalui [@BotFather](https://t.me/BotFather)
- **Telegram User ID** — dari [@userinfobot](https://t.me/userinfobot) atau [@RawDataBot](https://t.me/RawDataBot)
- **Anthropic API Key** *(opsional, sangat disarankan)* — dari [console.anthropic.com](https://console.anthropic.com) untuk mengaktifkan AI Brain (Jarwo), PeFi AI, `/optimize`, `/cron`, dan `/security report`

### Membuat Telegram Bot (Langkah demi Langkah)

1. Buka Telegram, cari **@BotFather**, kirim `/start`
2. Kirim `/newbot`
3. Beri nama bot (mis. `SyamAdmin Server`)
4. Beri username (harus diakhiri `bot`, mis. `syamvps_bot`)
5. BotFather membalas dengan **token** `123456789:ABCdef...` — **simpan, jangan bagikan**

**Mendapatkan User ID Anda:**

1. Cari **@userinfobot**, kirim pesan apa pun
2. Catat angka di field **Id** (contoh: `987654321`)
3. Angka inilah `TELEGRAM_ADMIN_ID` — bukan username

---

## 2. Instalasi

### Instalasi Cepat

```bash
# Upload dari komputer lokal ke server
scp syamadmin.tar.gz root@IP_SERVER:~/

# SSH masuk
ssh root@IP_SERVER

# Extract dan install
tar xzf syamadmin.tar.gz
cd syamadmin
chmod +x install.sh
sudo ./install.sh
```

Installer selesai dalam 1–3 menit dengan output berwarna per langkah.

### Apa yang Dilakukan Installer

1. Memverifikasi OS (Ubuntu 22.04/24.04)
2. Menginstall system dependencies: `python3`, `python3-venv`, `curl`, `wget`, `git`, `sqlite3`, `htop`, `rkhunter`, `lynis`
3. Membuat direktori kerja: `/opt/syamadmin/` (kode), `/etc/syamadmin/` (config), `/var/log/syamadmin/` (log), `/var/lib/syamadmin/` (database)
4. Membuat Python virtual environment di `/opt/syamadmin/venv/`
5. Menginstall Python packages dari `requirements.txt` (`python-telegram-bot`, `anthropic`, `psutil`, `aiosqlite`, `python-dotenv`, dll.)
6. Mendaftarkan systemd service `syamadmin` (auto-start saat boot)
7. Mengkonfigurasi logrotate
8. Database SQLite di-inisialisasi otomatis oleh tiap modul saat pertama jalan (self-sufficient — tidak perlu seeding manual)

---

## 3. Konfigurasi

Setelah instalasi, **wajib** edit konfigurasi sebelum menjalankan agent:

```bash
sudo nano /etc/syamadmin/config.env
```

> **Tip pemula:** `nano` adalah editor teks terminal. `Ctrl+O` lalu Enter = simpan, `Ctrl+X` = keluar.

Daemon membaca config dengan `override=True` — isi file ini **lebih berkuasa** daripada env shell yang terwarisi (mencegah `ANTHROPIC_API_KEY` lama di shell membayangi yang dikonfigurasi).

### Parameter Wajib

| Parameter | Contoh | Keterangan |
|-----------|--------|------------|
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdef...` | Token dari @BotFather |
| `TELEGRAM_ADMIN_ID` | `987654321` | Telegram User ID Anda (angka, bukan username) |

### Parameter AI (opsional, disarankan)

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `ANTHROPIC_API_KEY` | *(kosong)* | API key AI Brain. Tanpa ini, `/ai` pakai keyword parser sederhana |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Model Claude aktif (bisa diganti runtime via `/model`) |

### Identitas & Self-Update

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `SERVER_NAME` | `my-vps-01` | Nama server (tampil di notifikasi & `/status`) |
| `SERVER_TIMEZONE` | `Asia/Makassar` | Timezone server |
| `GITHUB_REPO` | `Syamsuddin/SyamAdmin` | Repo sumber untuk `/update` |
| `UPDATE_BRANCH` | `main` | Branch yang dipantau `/update` |

### Monitoring

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `ALERT_THRESHOLD_CPU` | `85` | Alert jika CPU > X% |
| `ALERT_THRESHOLD_RAM` | `90` | Alert jika RAM > X% |
| `ALERT_THRESHOLD_DISK` | `85` | Alert jika disk > X% |
| `ALERT_THRESHOLD_LOAD` | `4.0` | Alert jika load average > X |
| `MONITOR_INTERVAL` | `60` | Interval cek server (detik) |

### PeFi — Pre-Emptive Firewall

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `PEFI_ENABLED` | `true` | Aktif/nonaktif firewall pre-emptive |
| `PEFI_INTERVAL` | `60` | Interval siklus analisis traffic (detik) |
| `PEFI_AUTO_BLOCK` | `false` | Jika `true`, ancaman HIGH/CRITICAL confidence tinggi diblokir otomatis tanpa konfirmasi |
| `PEFI_AUTO_BLOCK_CONFIDENCE` | `0.95` | Ambang confidence untuk auto-block |
| `PEFI_THRESHOLD_CONN_PER_MIN` | `200` | Ambang koneksi/menit per-IP |
| `PEFI_THRESHOLD_PORT_SCAN` | `10` | Ambang jumlah port unik (deteksi port scan) |
| `PEFI_THRESHOLD_SYN` | `50` | Ambang SYN tanpa ACK (deteksi SYN flood) |
| `PEFI_THRESHOLD_SPIKE_MULTIPLIER` | `3.0` | Pengali lonjakan vs baseline |
| `PEFI_THRESHOLD_SSH_FAIL` | `20` | Ambang kegagalan login SSH (brute force) |
| `PEFI_THRESHOLD_HTTP_ERRORS` | `50` | Ambang error HTTP (deteksi recon/scanner) |
| `PEFI_TRUSTED_NETWORKS` | *(kosong)* | CIDR tepercaya tambahan, dipisah koma — tidak pernah diblokir |
| `PEFI_FP_AUTO_WHITELIST_COUNT` | `3` | Jumlah false-positive sebelum IP di-auto-whitelist |
| `PEFI_AI_COOLDOWN` | `300` | Rate-limit panggilan AI PeFi (detik) saat serangan panjang |
| `PEFI_NOTIF_COOLDOWN` | `1800` | Cooldown notifikasi per-IP (detik) |

### Lainnya

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `SSH_PORT` | `22` | Port SSH (dipakai modul security & firewall) |
| `BACKUP_DIR` | `/var/backups/syamadmin` | Direktori backup |
| `BACKUP_RETENTION_DAYS` | `7` | Retensi backup (hari) |
| `METRICS_RETENTION_DAYS` | `30` | Retensi metrik SQLite |
| `AUDIT_RETENTION_DAYS` | `90` | Retensi audit log & token usage |
| `CHAT_HISTORY_RETENTION_DAYS` | `14` | Retensi riwayat percakapan Memory Core |
| `LONG_TERM_MEMORY_MAX_ROWS` | `1000` | Batas baris pelajaran insiden |
| `PHP_VERSION` | `8.3` | Versi PHP yang diinstall provisioner |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Contoh Konfigurasi Minimal

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_ID=987654321
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
SERVER_NAME=vps-nustek-01
SERVER_TIMEZONE=Asia/Makassar
```

Simpan (`Ctrl+O`, Enter, `Ctrl+X`).

---

## 4. Menjalankan Agent

```bash
# Aktifkan auto-start saat boot + jalankan sekarang
sudo systemctl enable --now syamadmin

# Cek status
sudo systemctl status syamadmin

# Stop / Restart (restart wajib setelah edit config)
sudo systemctl stop syamadmin
sudo systemctl restart syamadmin
```

### Tiga Task Konkuren

Saat berjalan, agent menjalankan tiga task async sekaligus:

1. **SyamAdminBot** — loop polling Telegram (command router)
2. **SystemMonitor** — pengumpulan metrik + alert threshold
3. **PreEmptiveFirewall (PeFi)** — pengumpulan traffic, deteksi anomali, blokir berbasis AI

### Memantau Log

```bash
sudo journalctl -u syamadmin -f                 # log real-time
sudo tail -f /var/log/syamadmin/agent.log       # langsung dari file
```

### Verifikasi

Kirim `/start` ke bot. Anda akan menerima sapaan online; jika ini server baru, Jarwo menawarkan `/setup` dan `/profile setup`. Agent juga mengirim notifikasi startup otomatis.

---

## 5. Referensi Cepat Perintah

Perintah dikelompokkan sesuai menu Telegram. Banyak perintah punya **sub-command** — ketik perintah tanpa argumen (mis. `/site`, `/fw`, `/security`, `/pefi`) untuk sub-bantuan.

### 🖥 Server & Monitoring

| Perintah | Fungsi |
|----------|--------|
| `/status` | Dashboard lengkap: identitas, resource, layanan, keamanan, web stack, AI engine, Memory Core |
| `/services` | Status semua layanan terkelola |
| `/service restart\|stop\|start\|status\|reload <nama>` | Kontrol layanan langsung (tanpa AI) |
| `/logs [layanan] [baris]` | Lihat log: `nginx`, `nginx-access`, `mysql`, `auth`, `syslog`, `fail2ban`, `syamadmin` |
| `/audit` | 15 perintah terakhir yang dieksekusi agent |
| `/optimize` | Analisis tren 7 hari + rekomendasi tuning (AI, OTP untuk terapkan) |

### 🚀 Setup & Provisioning

| Perintah | Fungsi |
|----------|--------|
| `/setup` | Wizard onboarding server untuk pemula |
| `/provision` | Pasang LEMP stack dari awal (OTP) |

### 🌐 Manajemen Site

| Perintah | Fungsi |
|----------|--------|
| `/site wizard` | Wizard interaktif pembuatan situs |
| `/site add <domain> [framework]` | Tambah vhost Nginx (mis. `laravel`) |
| `/site list` | Daftar semua site terkelola |
| `/site ssl <domain>` | Aktifkan HTTPS via Let's Encrypt |
| `/site remove <domain>` | Hapus vhost (file web tetap ada, OTP) |

### 🔐 Keamanan & Firewall

| Perintah | Fungsi |
|----------|--------|
| `/security audit` | Audit keamanan komprehensif |
| `/security report` | Laporan ancaman cerdas (AI menganalisis Fail2Ban & auth.log) |
| `/security harden` | Hardening SSH + Fail2Ban + UFW + auto-update |
| `/security ssh-port <port>` | Pindah port SSH (OTP) |
| `/fw status` | Status UFW + semua rule |
| `/fw rules` | Daftar rule dengan nomor |
| `/fw allow <port>` | Buka port |
| `/fw deny <port>` | Tutup port (OTP bila port SSH) |

> Alias lama tetap jalan: `/harden`, `/security_report`, `/harden_ssh_port`, `/firewall`.

### 🛡️ PeFi — Pre-Emptive Firewall

| Perintah | Fungsi |
|----------|--------|
| `/pefi status` | Status & ringkasan PeFi |
| `/pefi threats` | Daftar ancaman aktif |
| `/pefi rules` | Aturan blokir aktif |
| `/pefi report [jam]` | Laporan periode (default 24 jam) |
| `/pefi health` | Kesehatan sistem PeFi |
| `/pefi scan` | Picu satu siklus analisis manual (OTP) |
| `/pefi block <ip> [jam]` | Blokir IP manual (OTP) |
| `/pefi unblock <ip>` | Hapus blokir (OTP) |
| `/pefi whitelist <ip> [alasan]` | Whitelist IP (OTP) |
| `/pefi ignore <threat_id>` | Tandai ancaman false-positive (OTP) |
| `/pefi autoblock on\|off` | Aktif/nonaktif auto-block (OTP) |

### 💾 Backup & Restore

| Perintah | Fungsi |
|----------|--------|
| `/backup` | Full backup: database + file web |
| `/backup db` | Backup database MySQL saja |
| `/backup files` | Backup file web + konfigurasi |
| `/backup list` | Daftar backup tersedia |
| `/restore <file>` | Pulihkan dari backup (OTP) |

### 🤖 AI & Otomatisasi

| Perintah | Fungsi |
|----------|--------|
| `/ai [perintah bebas]` | Perintah natural language; aksi tunggal ATAU rencana multi-langkah (autopilot) |
| `/cron [jadwal bebas]` | Penjadwalan natural language (mis. `backup db jam 3 pagi`) |
| `/token` | Statistik & estimasi biaya token Claude (USD & IDR) |
| `/model [haiku\|sonnet\|opus]` | Lihat & ganti model AI |
| *(teks bebas)* | Pesan tanpa `/` juga otomatis diproses Jarwo |

### 👤 Profil & Konteks

| Perintah | Fungsi |
|----------|--------|
| `/profile` | Lihat profil admin & konteks server |
| `/profile setup` | Wizard tanya-jawab pengisian profil |
| `/profile set <field> <nilai>` | Isi satu field |
| `/profile reset` | Hapus profil |

### ⚙️ Sistem

| Perintah | Fungsi |
|----------|--------|
| `/update [check\|now]` | Cek & pasang update SyamAdmin dari GitHub (OTP) |
| `/sysupdate` | Update & upgrade paket OS via apt (OTP) |
| `/reboot` | Reboot server (OTP) |
| `/confirm <OTP>` | Konfirmasi aksi berisiko |
| `/start` · `/help` | Selamat datang · daftar perintah |

---

## 6. Perintah Telegram — Panduan Lengkap

### `/status` — Dashboard Server

Dashboard kondisi server **secara lengkap** — bukan sekadar resource, tapi identitas, jaringan, keamanan, web stack, AI engine, dan memori agen. Semua bagian dirangkai paralel & gagal-aman (bagian yang perintahnya tak tersedia tampil `n/a` tanpa menggagalkan seluruh `/status`).

**Contoh output:**

```
🖥 SyamAdmin — Status Server
🏷 Server : vps-nustek-01  (host: srv01)
🐧 OS     : Ubuntu 22.04.4 LTS  • kernel 5.15.0-91
🌐 IP     : 10.0.0.5  (publik: 103.x.x.x)
⏱ Uptime : 14d 6h 32m

📊 Resource
CPU  [████░░░░░░] 38%  • 2 core • load 0.45/0.38/0.31
RAM  [██████░░░░] 62%  • 1.2/2.0 GB
Disk [███░░░░░░░] 34%  • 6.8/20.0 GB
Net  ↑4521MB ↓12845MB • proc 127

🔧 Layanan
🟢 nginx  🟢 mysql  🟢 php8.3-fpm  🟢 fail2ban  🟢 ssh

🔐 Keamanan & Jaringan
SSH port : 22
Firewall : 🟢 aktif (8 rule)
Port listen : 22, 80, 443, 3306
Fail2Ban : 🟢 aktif (3 IP diblokir)

🌐 Web Stack
LEMP: TERPASANG • Site terkelola: 2 (1 SSL)

🧠 AI Engine
Model : claude-haiku-4-5-20251001
API   : 🟢 aktif • 42 panggilan • ≈ $0.012 (Rp196)

💾 Memory Core
Chat: 16 turn • Pelajaran: 5 • Preferensi: 3
```

IP publik di-cache 1 jam (gagal-aman → `n/a` bila offline). Versi SyamAdmin aktif juga tampil di sini.

---

### `/services` & `/service` — Status & Kontrol Layanan

`/services` mengecek apakah semua layanan terkelola berjalan (`nginx`, `mysql`, `php8.3-fpm`, `fail2ban`, `ufw`, `ssh`).

`/service` mengontrol satu layanan **langsung tanpa AI** — lebih cepat & deterministik:

```
/service status nginx       → cek status
/service restart php8.3-fpm  → restart
/service reload nginx        → reload config (tanpa downtime)
/service start mysql         → start
/service stop fail2ban       → stop (OTP — berpotensi downtime)
```

`stop` selalu butuh OTP. Nama layanan divalidasi (hanya `a-z A-Z 0-9 @ . _ -`).

---

### `/logs [layanan] [baris]` — Lihat Log

Menampilkan baris terakhir log (default 30, bisa 1–200). Log `syamadmin` dibaca via `journalctl` dengan fallback ke file.

```
/logs                 → syslog
/logs nginx           → error log Nginx
/logs nginx-access    → access log Nginx
/logs mysql           → error log MySQL
/logs auth            → log login SSH
/logs fail2ban        → log Fail2Ban
/logs syamadmin       → log agen sendiri
/logs nginx 100       → 100 baris error Nginx
```

> **Tip:** log sulit dibaca? `/ai analisis error log nginx`.

---

### `/audit` — Log Aktivitas Agent

15 perintah shell terakhir yang dieksekusi agent, dengan timestamp, modul pemanggil, dan status (✅/❌).

---

### `/setup` — Wizard Onboarding (Pemula)

Wizard interaktif memandu server kosong menjadi siap pakai. Balas nomor langkah:

1. **Pasang LEMP (web server)**
2. **Amankan server** (hardening + firewall + Fail2Ban)
3. **Buat website pertama**

Ketik `1`/`2`/`3`, atau `selesai` untuk keluar.

---

### `/provision` — Setup LEMP Stack

Menginstall & mengkonfigurasi seluruh komponen web server. Memerlukan OTP karena besar & tidak bisa di-undo.

**Yang diinstall:**

| Komponen | Detail |
|----------|--------|
| **Nginx** | Web server: gzip, security headers, worker tuning |
| **MySQL 8** | Diamankan otomatis, password root digenerate 24 karakter acak |
| **PHP 8.3** | + extensions (fpm, mysql, mbstring, xml, curl, gd, zip, intl, bcmath, redis, opcache, dll.) |
| **Composer** | Dependency manager PHP |
| **Certbot** | SSL gratis Let's Encrypt |
| **Swap 2 GB** | Bila belum ada |

Password MySQL root disimpan di `/root/.my.cnf`. **Catat di tempat aman.** Proses 5–10 menit. Komponen yang sudah ada di-skip otomatis bila dijalankan ulang.

---

### `/site` — Manajemen Situs Web

```
/site wizard               → wizard interaktif tanya-jawab
/site add example.com      → vhost standar
/site add app.com laravel  → vhost Laravel (document root → public/)
/site list                 → daftar site
/site ssl example.com      → aktifkan HTTPS
/site remove example.com   → hapus vhost (OTP)
```

**Saat `add`:** membuat document root, `index.html` default, konfigurasi Nginx (PHP-FPM via Unix socket, security headers, clean URL `try_files`, deny file sensitif), PHP-FPM pool terisolasi per-site, mengaktifkan & reload Nginx, menyimpan ke DB. Untuk Laravel, root diarahkan ke `public/` dengan routing yang sesuai.

**Saat `ssl`:** terbit sertifikat Let's Encrypt, redirect HTTP→HTTPS, HSTS, auto-renewal via certbot timer. Prasyarat: DNS A record domain sudah mengarah ke IP server (`dig +short domain` → IP server) dan port 80 terbuka. Bila gagal, Jarwo otomatis menambahkan penjelasan ramah-pemula.

**Saat `remove`:** konfigurasi Nginx dihapus & site dinonaktifkan, tapi **file di `/var/www/` tetap ada** demi keamanan.

---

### `/security` — Audit, Laporan, Hardening, Port SSH

Router keamanan dengan empat sub-command (default `audit`).

**`/security audit`** — pemeriksaan menyeluruh: SSH password auth, root login, Fail2Ban, UFW, unattended-upgrades, open ports, package updates, login history.

**`/security report`** — Jarwo menganalisis `auth.log` & data Fail2Ban, lalu menyajikan **laporan intelijen ancaman** (pola serangan, IP berulang, saran).

**`/security harden`** — hardening menyeluruh dengan progress 4 langkah: SSH (password off, key-only, max 3 attempt, idle disconnect), Fail2Ban (jail SSH & Nginx), UFW (default deny incoming, izinkan 22/80/443), auto security updates.

> ⚠️ **Peringatan:** `/security harden` mematikan login SSH password. Pastikan SSH key sudah terpasang (`ssh-copy-id root@IP_SERVER`) atau Anda bisa terkunci dari server.

**`/security ssh-port <port>`** — pindah port SSH ke port non-standar (rentang 1024–65535) dengan OTP & verifikasi koneksi.

---

### `/fw` — Firewall UFW

```
/fw status        → status + semua rule
/fw rules         → daftar rule bernomor
/fw allow 3306    → buka port (MySQL)
/fw allow 6379    → buka port (Redis)
/fw deny 8080     → tutup port
```

Menutup port SSH (`/fw deny 22` atau port SSH aktif) memicu **peringatan + OTP** untuk mencegah lockout.

> **Tip:** buka hanya port yang benar-benar dibutuhkan.

---

### `/backup` & `/restore`

```
/backup            → full (DB + file)
/backup db         → database MySQL saja
/backup files      → file web + konfigurasi
/backup list       → daftar backup
/restore <file>    → pulihkan (OTP, destruktif)
```

Lihat [Backup & Restore](#14-backup--restore) untuk detail.

---

### `/optimize` — Analisis Kinerja & Rekomendasi (AI)

Jarwo membaca **tren historis 7 hari** dari database metrik, lalu menyusun analisis & rekomendasi tuning. Bila ada tindakan optimasi yang bisa diterapkan, ditampilkan perintahnya + tingkat risiko + OTP untuk menjalankan.

```
💡 Analisis Kinerja & Rekomendasi AI

RAM rata-rata 78% selama seminggu, puncak 91% tiap sore.
MySQL buffer pool masih default...

⚙️ Tindakan Optimasi Tersedia (mysql):
• Perintah: SET GLOBAL innodb_buffer_pool_size=...
• Risiko: rendah

Balas `4821` atau /confirm 4821 untuk melanjutkan (berlaku 60 detik).
```

---

### `/cron` — Penjadwalan Natural Language

Jadwalkan tugas berkala dalam bahasa bebas — Jarwo mengubahnya jadi ekspresi cron, menampilkan ringkasan, lalu meminta OTP.

```
/cron backup db setiap jam 3 pagi
/cron audit keamanan tiap hari minggu jam 11 malam
/cron scan rootkit tiap jam 12 malam
```

```
📅 Konfirmasi Penjadwalan Otomatis (AI)
• Tugas: backup_db
• Jadwal: Setiap hari pukul 03:00
• Ekspresi Cron: 0 3 * * *

Balas `7392` atau /confirm 7392 untuk melanjutkan.
```

---

### `/token` — Statistik Token AI

Konsumsi token Claude akumulatif + estimasi biaya (USD & IDR), berdasarkan tarif model aktif.

```
📊 Statistik Penggunaan Claude API
• Status API: 🟢 aktif
• Total Pemanggilan: 142
• Token Input: 198,340
• Token Output: 24,102
• Total Token: 222,442

💰 Estimasi Biaya Akumulatif:
• USD: $0.32063
• IDR: Rp 5,226.27
```

---

### `/model` — Lihat & Ganti Model AI

Tanpa argumen → daftar model terkini dengan harga per-MTok (USD & IDR) dan model aktif ditandai.

| Shorthand | Model | Tier | Catatan |
|-----------|-------|------|---------|
| `haiku` | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | fast | Default — cepat & hemat ($1/$5 per MTok) |
| `sonnet` | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | balanced | Keseimbangan terbaik ($3/$15 per MTok) |
| `opus` | Claude Opus 4.8 (`claude-opus-4-8`) | flagship | Paling canggih ($5/$25 per MTok) |

```
/model            → lihat daftar & model aktif
/model sonnet     → ganti ke Sonnet
/model claude-opus-4-8   → pakai ID penuh
```

Perubahan langsung aktif & disimpan ke `config.env`. Catatan: prompt caching efektif pada Sonnet/Opus (min ≥1024 token), inert pada Haiku pada ukuran prefix saat ini.

---

### `/profile` — Profil Admin & Konteks Server

Agar Jarwo lebih personal: menyapa dengan nama Anda, paham konteks kerja, zona waktu, dan gaya komunikasi. Lihat [Memory Core](#9-memory-core--personalisasi-agen).

```
/profile                       → lihat profil
/profile setup                 → wizard tanya-jawab
/profile set name Budi         → isi satu field
/profile set timezone Asia/Jakarta
/profile reset                 → hapus profil
```

**Field tersedia:** `name`, `nickname`, `job`, `organization`, `location`, `timezone`, `language` (id/en), `hobby`, `comm_style` (santai/formal/ringkas); plus konteks server: `role` (produksi/staging/dev), `purpose` (fungsi server). Field opsional bisa di-`lewati` di wizard.

---

### `/update`, `/sysupdate`, `/reboot`

Lihat [Self-Update & Update OS](#15-self-update--update-os).

```
/update            → cek versi terbaru di GitHub
/update now        → pasang update (backup + auto-rollback, OTP)
/sysupdate         → apt update && apt upgrade -y (OTP)
/reboot            → reboot server (OTP)
```

---

### `/confirm` — Konfirmasi Aksi Berbahaya

```
/confirm 4821      → konfirmasi dengan kode OTP
```

Lihat [Sistem Konfirmasi OTP](#16-sistem-konfirmasi-otp).

---

## 7. PeFi — Pre-Emptive Firewall Agent

PeFi adalah task konkuren yang berjalan terus-menerus: **mengumpulkan data traffic jaringan, mendeteksi anomali secara proaktif, dan memblokir ancaman sebelum serangan berhasil** — diperkuat analisis AI. Berbeda dari Fail2Ban yang reaktif (menunggu kegagalan login), PeFi menilai pola traffic dan dapat memblokir *sebelum* serangan mencapai tujuannya.

### Cara Kerja

Setiap `PEFI_INTERVAL` detik (default 60):

1. **Collector** — kumpulkan koneksi aktif, SYN, paket, error HTTP, kegagalan SSH per-IP
2. **Baseline Engine** — bangun baseline adaptif (EMA) dari traffic normal
3. **Anomaly Detector** — 6 pemeriksaan rule-based:

| Tipe | Deteksi |
|------|---------|
| `PORT_SCAN` | Satu IP menyentuh banyak port unik |
| `SYN_FLOOD` | Banyak SYN tanpa ACK |
| `BRUTE_FORCE` | Kegagalan login SSH berulang |
| `CONN_SPIKE` | Lonjakan koneksi vs baseline |
| `RECON` | Error HTTP tinggi (scanner/probing) |
| `RECIDIVIST` | IP yang sudah pernah jadi ancaman, kembali lagi |

4. **AI Verdict** — ancaman pending dikirim ke Claude untuk verdict (`BLOCK`/`MONITOR`/`IGNORE`) + confidence + alasan. Dibatasi rate-limit `PEFI_AI_COOLDOWN` agar tidak meledak saat serangan panjang.
5. **Aksi** — bila `PEFI_AUTO_BLOCK=true` dan verdict BLOCK dengan confidence ≥ `PEFI_AUTO_BLOCK_CONFIDENCE`, IP diblokir otomatis via UFW. Bila tidak, admin diberi notifikasi untuk konfirmasi manual.

Severity: `LOW` · `MEDIUM` · `HIGH` · `CRITICAL`. Notifikasi per-IP dibatasi `PEFI_NOTIF_COOLDOWN` agar tidak banjir.

### Perlindungan Bawaan

- **Trusted networks** — IP admin, jaringan privat, dan `PEFI_TRUSTED_NETWORKS` tidak pernah diblokir (anti self-lockout).
- **Feedback loop** — IP yang ditandai false-positive sebanyak `PEFI_FP_AUTO_WHITELIST_COUNT` kali di-auto-whitelist.
- **Cleanup** — rule UFW kedaluwarsa & data lama dipangkas berkala (`PEFI_CLEANUP_EVERY_TICKS`).

### Perintah

```
/pefi status              → ringkasan: enabled, auto-block, ancaman, blokir aktif
/pefi threats             → daftar ancaman aktif (severity diurutkan)
/pefi rules               → aturan blokir UFW yang dipasang PeFi
/pefi report [jam]        → laporan periode (default 24 jam)
/pefi health              → kesehatan internal (collector, baseline, DB)
/pefi scan                → picu satu siklus analisis manual (OTP)
/pefi block <ip> [jam]    → blokir IP manual, default 24 jam (OTP)
/pefi unblock <ip>        → hapus blokir (OTP)
/pefi whitelist <ip> [alasan]  → whitelist permanen (OTP)
/pefi ignore <threat_id>  → tandai ancaman false-positive (OTP)
/pefi autoblock on|off    → aktif/nonaktif auto-block (OTP)
```

> **Auto-block ON:** ancaman HIGH/CRITICAL dengan confidence ≥ 95% diblokir **tanpa** konfirmasi admin. **OFF:** semua blokir butuh konfirmasi manual. Default OFF — aktifkan setelah Anda yakin baseline sudah matang.

---

## 8. AI Brain & Jarwo — Natural Language

### Siapa Jarwo

Jarwo adalah persona AI Brain SyamAdmin: **sysadmin senior 15 tahun yang ramah, suka bercanda ringan tapi profesional**. Menyapa Anda dengan panggilan pilihan ("Boss Budi"), menyesuaikan salam dengan waktu nyata, proaktif memberi saran setelah tugas selesai, dan langsung mention bila melihat potensi masalah (CPU tinggi, disk hampir penuh, lama belum backup, service mati).

### Cara Pakai

```
/ai [perintah dalam bahasa bebas]
```

Pesan teks **tanpa** awalan `/` juga otomatis dikirim ke Jarwo — Anda tidak harus selalu mengetik `/ai`.

**Contoh:**

```
/ai restart nginx
/ai cek kenapa disk penuh
/ai tambah site portal.desa.id dengan laravel
/ai install redis-server
/ai buka port 6379 di firewall
/ai scan rootkit
/ai lihat siapa saja yang login hari ini
/ai berapa banyak koneksi MySQL aktif
/ai analisis error log nginx
```

### Alur Pemrosesan

```
Anda kirim → Jarwo kumpulkan Memory Core (server-state + preferensi + riwayat + pelajaran)
           → Claude API (native tool-use) tentukan aksi terstruktur
           → aksi tunggal  ATAU  rencana multi-langkah (steps[])
           → eksekusi (aksi/rencana berisiko → minta OTP)
           → CommandExecutor (safety filter + audit log)
           → hasil dilaporkan; percakapan & pelajaran disimpan ke memori
```

### Rencana Multi-Langkah (Autopilot)

Perintah majemuk dalam satu kalimat disusun jadi rencana berurutan dengan progress tracker langsung:

```
/ai backup database, lalu restart nginx, terakhir ubah port ssh ke 2222
```

```
🔄 Autopilot — Rencana Kerja
✅ 1/3 Backup semua database
⏳ 2/3 Restart service nginx
💤 3/3 Ubah port SSH ke 2222
```

- Bila **ada langkah berisiko**, seluruh rencana wajib **satu OTP** (balasan "ya" ditolak).
- Jika satu langkah gagal, sisa langkah **dibatalkan** dan Jarwo menjelaskan penyebabnya (*halt-on-failure*).
- Saat seluruh rencana sukses, ringkasannya disimpan sebagai *pelajaran* di Memory Core.

### Konfirmasi Perintah Berisiko

Setiap shell command bebas yang dipancarkan AI **dipaksa** berstatus destruktif (wajib OTP) — safety filter statis saja tidak dipercaya untuk perintah destruktif-tapi-belum-terblokir.

### Fallback Mode (tanpa API Key)

Tanpa `ANTHROPIC_API_KEY`, AI Brain memakai keyword parser sederhana. Masih dikenali: `status`, `service/layanan`, `provision/lemp`, `firewall/ufw`, `security/audit`, `backup`, `restart nginx/mysql/php`, `disk/storage`. Untuk kemampuan penuh (perintah kompleks, pemahaman konteks, persona Jarwo, PeFi AI, `/optimize`, `/cron`, `/security report`), pasang API key.

---

## 9. Memory Core — Personalisasi Agen

Memory Core membuat Jarwo makin relevan seiring waktu. Empat pilar:

| Pilar | Sumber | Isi |
|-------|--------|-----|
| **1. Server State** | `monitor.get_state_context()` | Kondisi server real-time (resource, layanan, LEMP) |
| **2. Preferensi** | `user_memory` | Preferensi admin (mis. versi PHP favorit) |
| **3. Riwayat Chat** | `chat_history` | 8 turn percakapan terakhir (sliding window) |
| **4. Pelajaran** | `long_term_memory` (FTS5) | Pelajaran dari insiden/konfigurasi, dicari berdasarkan relevansi |

Di samping itu ada **Profil admin** (`profile.*`) dan **konteks server** (`server.*`) dari `/profile`, plus **konteks waktu** (tanggal/hari/jam real di timezone admin — volatile, tak pernah di-cache).

> **Keamanan memori:** `redact_secrets()` menyensor key/token/password **sebelum** apa pun disimpan ke SQLite. Wizard provisioning yang menampilkan password DB pun tidak akan tersimpan plaintext di memori.

---

## 10. Alur Kerja Umum

### Skenario A: Setup Server Baru dari Nol

```
1. /start                    → verifikasi online; Jarwo tawarkan /setup & /profile
2. /profile setup            → kenalan dulu (opsional tapi disarankan)
3. /provision → /confirm <OTP>   → LEMP 5–10 menit, catat password MySQL!
4. (pastikan SSH key terpasang) /security harden
5. /status · /services · /security audit   → verifikasi
6. /site add example.com → /site ssl example.com
7. /pefi status              → pastikan firewall pre-emptive aktif
```

### Skenario B: Menambah Site

```
/site add toko.example.com
/site ssl toko.example.com
→ upload file ke /var/www/toko.example.com/public_html/
```

Laravel:

```
/site add app.com laravel    → document root di /var/www/app.com/public/
/site ssl app.com
```

### Skenario C: Disk Penuh

```
Alert otomatis: 🔴 CRITICAL — Disk 92% (18.4/20.0 GB)

Anda: /ai cek folder apa yang paling banyak makan disk
Jarwo: /var/log 4.2 GB · /var/www 8.1 GB · /var/backups 5.9 GB

Anda: /ai hapus log lama di /var/log lebih dari 30 hari
Jarwo: ⚠️ butuh OTP (perintah shell destruktif)
Anda: <OTP>
Jarwo: ✅ Beres boss, disk turun ke 61%.
```

### Skenario D: Monitoring Harian (Pasif)

Agent otomatis cek resource & layanan tiap 60 detik, PeFi memantau traffic, dan kirim alert bila perlu. Cek manual kapan saja: `/status`, `/services`, `/pefi status`, `/logs nginx`.

### Skenario E: Service Down

```
Alert: 🔴 CRITICAL — Service nginx DOWN
Anda: /ai restart nginx   (atau /service restart nginx)
Jarwo: ✅ nginx active (running).
(jika masih bermasalah) /ai analisis kenapa nginx gagal start
```

---

## 11. Monitoring & Alert

Background loop mengumpulkan metrik tiap `MONITOR_INTERVAL` detik dan menyimpannya ke SQLite untuk analisis tren (dipakai `/optimize`).

| Metrik | Default | Alert |
|--------|---------|-------|
| CPU | > 85% | Tampilkan top processes |
| RAM | > 90% | Used/total |
| Disk | > 85% | ⚠️ CRITICAL |
| Load | > 4.0 | Load average |
| Service down | — | ⚠️ CRITICAL + saran restart |

**Cooldown:** alert yang sama tidak dikirim ulang dalam 5 menit (anti-spam). **Retensi:** data lama dipangkas otomatis oleh `SystemMonitor._prune_old_data()` (sekali/24 jam).

---

## 12. Keamanan & Hardening

### Setelah `/security harden`

**SSH:** password auth off (key-only), root `prohibit-password`, max 3 attempt, idle disconnect 5 menit, X11/agent/TCP forwarding off.
**Fail2Ban:** SSH brute force 3 attempt → ban 2 jam; Nginx HTTP auth 3 attempt → ban 1 jam; bot scanner & rate limit aktif.
**UFW:** default deny incoming, allow outgoing, hanya 22/80/443 dibuka.
**Nginx:** `server_tokens off`, security headers, deny `.env`/`.git`/`.htaccess`; dengan SSL → HSTS, TLS 1.2/1.3, cipher modern.
**PHP:** header `X-Powered-By` disembunyikan.

### Tiga Lapis Pertahanan

1. **Fail2Ban** — reaktif, mem-ban setelah kegagalan login berulang
2. **PeFi** — pre-emptive, memblokir pola serangan sebelum berhasil
3. **UFW** — kontrol akses port dasar

### Rutinitas Disarankan

| Frekuensi | Tindakan |
|-----------|----------|
| Harian | `/pefi status` — pantau ancaman |
| Mingguan | `/security audit` + `/security report` |
| Mingguan | `/backup` — full backup manual |
| Mingguan | `/optimize` — review tren & tuning |
| Saat ada rilis | `/update check` |

---

## 13. Manajemen Site & SSL

### Struktur Direktori

```
/var/www/example.com/
└── public_html/          ← document root (default)
    └── index.html

/var/www/myapp.com/
└── public/               ← document root (Laravel)
    └── index.php
```

### Konfigurasi Nginx Otomatis

PHP-FPM via Unix socket, security headers, static asset caching (30 hari), deny file tersembunyi (`.env`, `.git`, `.htaccess`), clean URL `try_files` (kompatibel Laravel/WordPress/CodeIgniter).

### SSL (Let's Encrypt)

Redirect HTTP→HTTPS, TLS 1.2/1.3, HSTS (max-age 2 tahun), OCSP stapling, auto-renewal via certbot timer.

**Prasyarat:** DNS A record → IP server (`dig +short example.com`), port 80 terbuka (`/fw allow 80`), rate limit Let's Encrypt max 5 sertifikat/domain/minggu.

---

## 14. Backup & Restore

### Lokasi

```
/var/backups/syamadmin/
├── db/      all_databases_YYYYMMDD_HHMMSS.sql.gz
└── files/   webfiles_YYYYMMDD_HHMMSS.tar.gz
```

### Yang Dibackup

**Database (`/backup db`):** semua DB MySQL via `mysqldump --all-databases --single-transaction --routines --triggers`, dikompresi gzip (konsisten tanpa lock).
**File (`/backup files`):** `/var/www/`, `/etc/nginx/`, `/etc/php/`.

### Restore

Lewat Telegram (OTP): `/restore <file>`. File `.sql.gz` → restore ke MySQL; `.tar.gz` → ekstrak ke sistem. **Destruktif** — menimpa data saat ini.

Manual:

```bash
gunzip < /var/backups/syamadmin/db/all_databases_*.sql.gz | mysql -u root
tar xzf /var/backups/syamadmin/files/webfiles_*.tar.gz -C /
```

### Retensi

Backup lebih lama dari `BACKUP_RETENTION_DAYS` (default 7) dihapus otomatis tiap full backup.

---

## 15. Self-Update & Update OS

### `/update` — Self-Update SyamAdmin dari GitHub

Memperbarui kode SyamAdmin in-band, tanpa SSH:

```
/update            → cek VERSION lokal vs GitHub (raw)
/update now        → pasang (OTP)
```

Proses `/update now`: **backup → unduh tarball branch dari GitHub → `cp -a` over `/opt/syamadmin` (mempertahankan `venv`/config/db) → `pip install -r requirements.txt` → restart → health-check → auto-rollback bila gagal**. Bot restart sebentar; hasil akhir dikirim otomatis ke Telegram. Sumber diatur via `GITHUB_REPO` & `UPDATE_BRANCH`.

### `/sysupdate` — Update Paket OS

Menjalankan `apt-get update` lalu `apt-get upgrade -y` (OTP). Untuk memperbarui paket sistem Ubuntu — terpisah dari self-update aplikasi.

### `/reboot`

Reboot server (OTP). Bot tidak merespons hingga server kembali online.

---

## 16. Sistem Konfirmasi OTP

Operasi berisiko mengatur **pending confirmation** dengan kode OTP 4-digit (kriptografis) dan timeout 60–120 detik. Dua tingkat:

**Non-destruktif** (`ai`, `add_cron`, `optimize_system`, `profile_reset`): menerima kata afirmatif (`ya/iya/ok/oke/yes/y/lanjut/setuju/gas`) **ATAU** kode OTP.

**Destruktif** (`provision`, `remove_site`, `deny_ssh`, `change_ssh_port`, `restore`, `service_stop`, `reboot`, `apt_upgrade`, `app_update`, semua `pefi_*`): **wajib kode OTP**. Kata afirmatif ditolak.

**Perintah AI bebas:** setiap shell command yang dipancarkan model dipaksa destruktif (wajib OTP). **Rencana multi-langkah:** butuh OTP bila ada satu langkah saja di luar allowlist read-only.

Konfirmasi: balas angka OTP langsung, atau `/confirm <OTP>`. Frasa konsisten: *"Balas `4821` atau kirim `/confirm 4821` untuk melanjutkan (berlaku 60 detik)."*

---

## 17. Struktur File & Direktori

### Kode (di Server)

```
/opt/syamadmin/
├── syamadmin.py             # Entry point daemon (3 task konkuren)
├── VERSION                  # Versi untuk /update & /status
├── venv/                    # Python virtual environment
├── modules/
│   ├── brain.py             # AI Brain (Jarwo): Claude tool-use, Memory Core, model & profil
│   ├── telegram_bot.py      # Command router, wizard, autopilot, /status
│   ├── pefi.py              # Pre-Emptive Firewall Agent
│   ├── executor.py          # Safe shell executor + safety filter + audit log
│   ├── monitor.py           # Metrics loop, alert, state context, prune
│   ├── notifier.py          # Pengirim notifikasi Telegram
│   ├── provisioner.py       # Installer LEMP
│   ├── security.py          # Hardening, audit, rootkit scan, ssh-port, report
│   ├── firewall.py          # Manajemen rule UFW
│   ├── site_manager.py      # Nginx vhost, PHP-FPM, SSL
│   ├── backup.py            # MySQL dump & file backup
│   └── updater.py           # Self-update dari GitHub
├── templates/               # nginx_vhost.conf, nginx_ssl.conf, php_fpm_pool.conf
└── scripts/                 # harden_ssh.sh, setup_fail2ban.sh, setup_swap.sh, update.sh
```

### Konfigurasi & Data

```
/etc/syamadmin/config.env         # Konfigurasi (permission 600)
/var/log/syamadmin/agent.log      # Log agent
/var/lib/syamadmin/syamadmin.db   # SQLite (audit, metrics, sites, memory, token, PeFi)
/var/backups/syamadmin/           # Backup
/etc/systemd/system/syamadmin.service
```

### Tabel SQLite

`audit_log` (executor), `metrics` (monitor), `sites` (site_manager), `token_usage` · `user_memory` · `chat_history` · `long_term_memory`+`long_term_fts` (brain), `pefi_threats` + tabel PeFi (pefi). Tiap modul membuat tabelnya sendiri secara idempoten.

---

## 18. Troubleshooting

### Agent Tidak Merespons

```bash
sudo systemctl status syamadmin
sudo journalctl -u syamadmin -n 50          # cari ERROR/CRITICAL
sudo systemctl restart syamadmin
# Debug manual (error langsung terlihat):
sudo systemctl stop syamadmin
sudo /opt/syamadmin/venv/bin/python3 /opt/syamadmin/syamadmin.py
```

Cek: `TELEGRAM_BOT_TOKEN` benar? `TELEGRAM_ADMIN_ID` angka (bukan username)? Internet aktif (`ping 8.8.8.8`)?

### "Unauthorized"

Hanya `TELEGRAM_ADMIN_ID` yang cocok yang bisa memakai bot. Verifikasi ID via [@userinfobot](https://t.me/userinfobot) dan samakan dengan config.

### Provision Gagal di Tengah

```bash
sudo tail -100 /var/log/syamadmin/agent.log
sudo rm -f /var/lib/dpkg/lock-frontend && sudo dpkg --configure -a
```

Jalankan ulang `/provision` — komponen terinstall di-skip.

### SSL Gagal

| Penyebab | Cek | Solusi |
|----------|-----|--------|
| DNS belum propagasi | `dig +short example.com` | Tunggu 5–60 menit |
| Port 80 diblokir | `curl http://example.com` | `/fw allow 80` |
| Rate limit Let's Encrypt | error "too many certificates" | Tunggu 1 minggu |

### PeFi Memblokir IP yang Salah

```
/pefi unblock <ip>             → buka blokir
/pefi whitelist <ip> alasan    → cegah blokir ulang
/pefi ignore <threat_id>       → tandai false-positive (auto-whitelist setelah N kali)
```

Tambahkan jaringan kantor Anda ke `PEFI_TRUSTED_NETWORKS` di config.

### Update Gagal

`/update now` punya **auto-rollback** — bila health-check gagal, versi lama dipulihkan dari backup otomatis. Cek log: `sudo tail -50 /var/log/syamadmin/update.log`.

### AI Brain Error

Pastikan `ANTHROPIC_API_KEY` valid & ada kredit. AI Brain otomatis fallback ke keyword parser bila API gagal — perintah dasar tetap jalan.

### Database SQLite Corrupt

```bash
cp /var/lib/syamadmin/syamadmin.db{,.bak}
sqlite3 /var/lib/syamadmin/syamadmin.db "PRAGMA integrity_check;"
# Bila corrupt (data historis hilang, agent tetap normal):
rm /var/lib/syamadmin/syamadmin.db && sudo systemctl restart syamadmin
```

### Terkunci dari Server (SSH)

Bila `/security harden` dijalankan tanpa SSH key:

1. Login via **console VPS** (panel provider)
2. `sudo nano /etc/ssh/sshd_config` → `PasswordAuthentication yes`
3. `sudo systemctl restart sshd`
4. Tambahkan SSH key, lalu `/security harden` lagi

---

## 19. Keamanan Agent

### Command Safety Filter

Setiap shell command melewati `CommandExecutor._is_blocked()` (regex blacklist + tokenisasi `shlex`, termasuk interpreter bersarang) **sebelum** dieksekusi — tidak bisa dilewati, bahkan via `/ai`.

| Diblokir permanen | Alasan |
|-------------------|--------|
| `rm -rf /` | Hapus seluruh filesystem |
| `mkfs.*` | Format disk |
| `> /dev/sda` | Tulis ke raw disk |
| `:(){:\|:&};:` | Fork bomb |
| `chmod -R 777 /` | Buka semua permission |
| `curl \| bash` | Eksekusi kode dari internet tanpa verifikasi |

### Audit Trail

Setiap perintah dicatat: timestamp, modul, perintah (≤200 char), durasi, User ID Telegram, status (success/failed/blocked/timeout). Lihat via `/audit` atau:

```bash
sqlite3 /var/lib/syamadmin/syamadmin.db \
  "SELECT timestamp, module, action, status FROM audit_log ORDER BY id DESC LIMIT 20;"
```

### Access Control

Satu admin (`TELEGRAM_ADMIN_ID`). Percobaan akses lain dicatat sebagai security event. Operasi berbahaya butuh OTP (timeout 60–120 detik). Config permission `600` (root-only). Rahasia disensor sebelum masuk memori.

---

## 20. Glosarium

| Istilah | Penjelasan |
|---------|------------|
| **VPS** | Virtual Private Server |
| **LEMP** | Linux + Nginx + MySQL + PHP — stack web standar |
| **Jarwo** | Persona AI sysadmin SyamAdmin (Claude) |
| **PeFi** | Pre-Emptive Firewall Agent — blokir serangan secara proaktif |
| **Memory Core** | Memori 4-pilar yang membuat Jarwo makin relevan |
| **OTP** | One-Time Password 4-digit untuk konfirmasi aksi berisiko |
| **Autopilot** | Rencana multi-langkah yang dijalankan AI berurutan |
| **SSH key** | Pasangan kunci kriptografi pengganti password SSH |
| **Nginx** | Web server |
| **PHP-FPM** | PHP FastCGI Process Manager |
| **MySQL** | Database server |
| **UFW** | Uncomplicated Firewall |
| **Fail2Ban** | Pemblokir IP brute force (reaktif) |
| **SSL/TLS** | Enkripsi HTTPS |
| **Let's Encrypt** | Penyedia sertifikat SSL gratis |
| **Certbot** | Tool pembuatan & pembaruan sertifikat |
| **systemd** | Manajer service Linux |
| **SQLite** | Database ringan berbasis file |
| **vhost** | Virtual host — konfigurasi Nginx per domain |
| **Document root** | Folder file web yang diakses pengunjung |
| **Load average** | Beban rata-rata server 1/5/15 menit |
| **Composer** | Manajer paket PHP |
| **token** | Unit konsumsi Claude API (dasar perhitungan biaya) |

---

*SyamAdmin v3.2 — dibuat oleh @syams_ideris untuk menyederhanakan hidup sysadmin.*
*Made in Banjarmasin — South Kalimantan 🇮🇩*
</content>
</invoke>
