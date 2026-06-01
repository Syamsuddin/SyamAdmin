# SyamAdmin — Executive Summary

> **AI-Powered Server Management via Telegram**
> Dari perintah chat biasa → server produksi yang aman, optimal, dan terpantau 24/7.

---

## Masalah yang Kami Selesaikan

Mengelola server Linux adalah pekerjaan yang mahal, teknis, dan berisiko tinggi. Perusahaan kecil hingga menengah menghadapi tiga hambatan nyata:

| Masalah | Dampak Bisnis |
|---|---|
| Dibutuhkan sysadmin berpengalaman yang mahal | Biaya SDM tinggi, sulit direkrut |
| Perintah server yang kompleks dan mudah salah | Downtime, data loss, kerentanan keamanan |
| Tidak ada monitoring 24/7 yang terjangkau | Insiden tidak terdeteksi hingga terlambat |

**Solusi yang ada saat ini** (cPanel, Plesk, RunCloud) memerlukan antarmuka web yang rumit, lisensi tahunan mahal, dan tetap membutuhkan keahlian teknis untuk konfigurasi lanjutan.

---

## Solusi: SyamAdmin v3.0

**SyamAdmin** adalah agen AI sysadmin yang berjalan langsung di VPS Ubuntu Anda — dikendalikan sepenuhnya melalui **chat Telegram**, dalam **bahasa Indonesia atau Inggris**.

Tidak perlu masuk ke terminal. Tidak perlu hafal perintah Linux. Cukup kirim pesan.

```
Admin:  "backup database, lalu restart nginx, audit keamanan"
Bot:    ✅ 1/3 Backup database selesai (245 MB)
        ✅ 2/3 Nginx berhasil direstart
        ✅ 3/3 Audit keamanan: 0 kerentanan kritis ditemukan
```

---

## Proposisi Nilai Utama

### 1. Satu Orang Bisa Kelola Banyak Server
Seorang non-engineer sekalipun dapat mengelola server produksi sepenuhnya dari Telegram. Tidak diperlukan akses SSH atau pengetahuan Linux mendalam.

### 2. Menghemat Biaya Operasional Signifikan
Biaya sysadmin freelance: Rp 500.000–2.000.000/hari. SyamAdmin berjalan dengan biaya Claude API kurang dari **Rp 500/hari** untuk penggunaan normal (Claude Haiku 4.5, ~$0.03/hari).

### 3. Respons Insiden dalam Hitungan Detik
Monitor berjalan setiap 60 detik. Jika Nginx atau MySQL crash, SyamAdmin:
- Mendeteksi crash secara otomatis
- Menganalisis log error dengan AI
- Mengirim notifikasi beserta tombol one-click repair ke Telegram Anda

### 4. Keamanan Enterprise, Tanpa Kompleksitas Enterprise
Setiap aksi kritis (hapus site, ganti port SSH, restore backup) dilindungi **OTP 4-digit** yang kedaluwarsa dalam 60 detik. Aksi destruktif tidak bisa disetujui hanya dengan "ya" — harus kode numerik. Semua command yang dieksekusi tercatat di audit log SQLite.

---

## Fitur Unggulan

| Fitur | Apa yang Dilakukan |
|---|---|
| **AI Autopilot** | Satu kalimat → rencana multi-langkah → dieksekusi otomatis dengan live progress |
| **Memory Core** | Mengingat preferensi admin, riwayat percakapan, dan pelajaran dari insiden sebelumnya |
| **Auto-Repair** | Mendeteksi service crash, diagnosis AI, tawarkan perbaikan one-click |
| **Website Wizard** | Setup domain + PHP-FPM + database MySQL + SSL dalam satu percakapan terpandu |
| **NLP Cron Scheduler** | "Backup DB setiap Senin jam 3 pagi" → ditulis ke crontab otomatis |
| **Resource Optimizer** | Analisis tren 7 hari → rekomendasi tuning Nginx/MySQL/PHP dengan satu OTP untuk apply |
| **Security Scanner** | Laporan ancaman dari auth.log + Fail2Ban: IP penyerang, negara asal, port yang diserang |
| **SSH Port Tuner** | Pindah port SSH dengan 5 lapisan safety check + rollback otomatis jika gagal |
| **IPv6 Adaptive** | Deteksi otomatis dukungan IPv6 di VPS, konfigurasi Nginx disesuaikan tanpa sentuhan manual |

---

## Arsitektur Teknis (Ringkas)

```
Telegram Chat  →  AI Brain (Claude Haiku 4.5)  →  Safety Filter  →  Ubuntu Services
                       ↕                                                      ↕
                  Memory Core                                          SQLite Audit Log
              (Preferensi, Riwayat,                            (Setiap perintah tercatat)
               Pelajaran Insiden)
```

- **Runtime**: Python 3.10+ asyncio daemon, berjalan sebagai `systemd` service
- **AI Engine**: Anthropic Claude Haiku 4.5 dengan native tool-use (output JSON terstruktur, tidak ada string parsing yang rapuh)
- **Database**: SQLite lokal — audit log, metrik historis, memori AI, riwayat chat
- **Stack yang Dikelola**: Nginx, MySQL 8, PHP 8.3-FPM, UFW, Fail2Ban, Let's Encrypt

---

## Target Pengguna

| Segmen | Kasus Penggunaan |
|---|---|
| **Startup & UMKM** | Hosting website/aplikasi sendiri tanpa biaya sysadmin tetap |
| **Developer Freelance** | Kelola server klien dari mana saja via Telegram |
| **Agensi Digital** | Satu orang kelola puluhan server dengan akses terpusat |
| **IT Internal Perusahaan** | Kurangi ketergantungan pada sysadmin senior untuk tugas rutin |

---

## Model Biaya

| Komponen | Biaya |
|---|---|
| SyamAdmin (perangkat lunak) | **Gratis & Open Source** (GNU GPL v2) |
| VPS Ubuntu minimal | Rp 50.000–150.000/bulan (1 GB RAM, 1 vCPU) |
| Anthropic API (Claude Haiku) | ~$0.03/hari untuk penggunaan normal ≈ **Rp 15.000/bulan** |
| Telegram Bot API | Gratis |
| **Total operasional** | **< Rp 200.000/bulan** per server |

Bandingkan dengan: sysadmin freelance Rp 3–10 juta/bulan, atau lisensi cPanel/Plesk $15–30/bulan (tanpa fitur AI).

---

## Keunggulan Kompetitif

| Aspek | SyamAdmin | cPanel/Plesk | RunCloud |
|---|---|---|---|
| Antarmuka | Chat Telegram (natural) | Web UI | Web UI |
| Bahasa Indonesia | Native | Tidak | Tidak |
| AI Planning & Memory | Ya | Tidak | Tidak |
| Auto-Repair AI | Ya | Tidak | Terbatas |
| Biaya software | Gratis | $15–30/bln | $8–12/bln |
| Deploy di VPS sendiri | Ya | Tidak | Tidak |
| Open Source | Ya | Tidak | Tidak |

---

## Traction & Status

- **Versi saat ini**: v3.0 (Memory Core & Autopilot) — production-ready
- **Platform**: Ubuntu 22.04 LTS dan 24.04 LTS
- **Instalasi**: One-command installer (`./install.sh`) — server siap dalam < 15 menit
- **Commands**: 19+ perintah Telegram + free-text AI routing
- **Keamanan**: Dual-layer (OTP + safety filter regex/shlex) + audit log lengkap

---

## Roadmap 6 Bulan ke Depan

| Prioritas | Fitur |
|---|---|
| Q3 2026 | Multi-server management dari satu bot |
| Q3 2026 | Web dashboard lokal untuk visualisasi metrik |
| Q4 2026 | Docker container monitoring |
| Q4 2026 | Webhook CI/CD pipeline integration |
| Q4 2026 | Multi-admin dengan role-based permissions |
| Q1 2027 | Integrasi Grafana / Uptime Kuma |

---

## Call to Action

SyamAdmin siap deploy hari ini di VPS mana pun. Instalasi membutuhkan waktu kurang dari 15 menit.

**Langkah memulai:**
1. Siapkan VPS Ubuntu 22.04/24.04 (minimal 1 GB RAM)
2. Buat Telegram Bot via @BotFather
3. Jalankan `./install.sh` dan isi konfigurasi
4. Kirim `/start` ke bot — server siap dikelola via chat

**Kontak & Repositori:**
- GitHub: [github.com/Syamsuddin/SyamAdmin](https://github.com/Syamsuddin/SyamAdmin)
- Email: syamsuddin.ideris@gmail.com
- Dibuat dengan ☕ di Kalimantan, Indonesia 🇮🇩

---

> *"Built for sysadmins who'd rather chat than SSH."*
> SyamAdmin — Server management, sesuai cara kerja Anda.
