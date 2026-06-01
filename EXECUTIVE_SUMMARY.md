# SyamAdmin — Executive Summary

> **AI-Powered Sysadmin via Telegram**  
> Dari perintah chat biasa → server produksi aman, optimal, terpantau 24/7 — tanpa SSH, tanpa terminal, tanpa sysadmin mahal.

---

## Masalah yang Kami Selesaikan

Mengelola server Linux adalah pekerjaan teknis, mahal, dan berisiko tinggi:

| Masalah | Dampak |
|---|---|
| **Dibutuhkan sysadmin senior yang mahal** | Biaya Rp 500–2.000.000/hari; sulit direkrut di Indonesia |
| **Perintah kompleks, mudah salah** | Downtime, data loss, kerentanan keamanan akibat typo |
| **Monitoring 24/7 tidak ada atau mahal** | Insiden terdeteksi terlambat; kerugian finansial besar |
| **Interface panel (cPanel, Plesk) rumit** | Kurva belajar curam; support mahal; biaya lisensi tahunan |

---

## Solusi: SyamAdmin v3.0 — Memory Core + AI Autopilot + Self-Update

**SyamAdmin** = daemon Python yang berjalan di `/opt/syamadmin` di VPS Ubuntu Anda, dikendalikan **sepenuhnya via Telegram**, **dalam Bahasa Indonesia**. Tidak ada dashboard web. Tidak perlu SSH. Tidak perlu terminal.

```
Admin:  "/ai backup database, restart nginx, audit keamanan"
Bot:    🧠 Menyusun rencana...
        ✅ 1/3 Backup database: 245 MB selesai
        ✅ 2/3 Nginx restarted
        ✅ 3/3 Audit keamanan: skor A (0 kritis)
```

---

## 4 Pilar Keunggulan Kompetitif

### 1. **AI Native Tool-Use** — Rencana Multi-Langkah Otomatis
Satu kalimat natural language → Claude AI merancang rencana → dijalankan step-by-step dengan live progress. Gagal di step N? AI menganalisis error, menyarankan rollback atau perbaikan; semua tersimpan untuk belajar di masa depan.

**Contoh:** `"/ai setup wordpress dengan domain baru, database, SSL, dan cache Redis"`

### 2. **Memori Permanen** — Konteks Server + User Profile
Sistem mencatat (SQLite):
- **Pilar 1:** Setiap shell command (audit log + performa)
- **Pilar 2:** Preferensi admin (PHP version, timezone, gaya komunikasi — nama, panggilan, pekerjaan)
- **Pilar 3:** Chat history 8-turn (multi-turn context untuk AI)
- **Pilar 4:** Pelajaran insiden (FTS5 full-text search — AI cari solusi dari kejadian sebelumnya)

AI menjadi lebih "pintar" seiring waktu tanpa mengorbankan privasi (DB lokal, bukan cloud).

### 3. **Self-Update dari GitHub** — Zero Downtime
`/update check` — deteksi rilis baru dari GitHub v3.x → `/update now` triggernya:
- Backup otomatis
- Unduh tarball dari branch `main`
- Ganti file (keep `venv`, config, database)
- Restart service
- Health-check + auto-rollback jika gagal
- Kirim notifikasi hasil akhir ke Telegram

Tidak perlu menghubungi admin atau restart manual. Deploy update dalam seketika dari chat.

### 4. **Keamanan Berlapis** — OTP Destruktif + Safety Filter
- **Central OTP**: Setiap aksi destruktif (hapus site, ganti port SSH, restore, reboot, update) butuh 4-digit OTP berusia 60–120 detik
- **Dual-layer check**:
  - Regex + shlex tokenization filter memblokir injection (`; rm -rf /`, heredoc pipe-to-shell)
  - Aksi destruktif **menolak kata afirmatif** (`ya/ok`) — **harus numerik OTP**
  - Non-destruktif boleh menerima `ya`
- **Audit log**: Setiap command tercatat dengan timestamp, module, status, user

---

## Fitur Unggulan (v3.1)

### Manajemen Server Inti

| Fitur | Deskripsi |
|---|---|
| **`/status`** | Dashboard lengkap: identitas server + resource bars (CPU/RAM/Disk/Load) + status layanan + SSL ports + Fail2Ban + Recent logins + AI engine state |
| **`/services`** | Health check all managed services (nginx, mysql, php-fpm, fail2ban, ufw, ssh) |
| **`/service <action> <name>`** | Direct systemctl control: restart/start/stop/reload/status (stop butuh OTP) |
| **`/logs [layanan] [baris]`** | Read N tail lines (default 30, max 200) dari: nginx/nginx-access/mysql/auth/syslog/fail2ban/syamadmin |
| **`/audit`** | Riwayat 15 shell command terbaru (module, action, status, waktu) |
| **`/update check`** | Cek versi terbaru di GitHub (v3.1.0 vs v3.2.0?) |
| **`/update now`** | Pull & install dari GitHub + backup + auto-rollback (OTP) |
| **`/sysupdate`** | `apt-get update && upgrade -y` (OTP) |
| **`/reboot`** | Restart server (OTP) |

### Setup & Onboarding

| Fitur | Deskripsi |
|---|---|
| **`/start`** | Greeting personal (dengan nama admin dari profil); tawarkan `/setup` atau `/profile setup` jika ada yang baru |
| **`/setup`** | Wizard 6-langkah: check OS → dependencies → LEMP stack → firewall → SSL → health test |
| **`/provision`** | Install ulang LEMP Stack dari awal (7 tahap: Update → Nginx → MySQL 8 → PHP 8.3 + 14 ext → Composer → Certbot → Swap 2GB) |
| **`/profile [setup\|set <field> <val>\|reset]`** | Isi identitas admin (nama, panggilan, pekerjaan, lokasi, timezone, hobi) untuk personalisasi AI + konteks waktu sistem |

### Manajemen Website

| Fitur | Deskripsi |
|---|---|
| **`/site add <domain> [framework]`** | Create Nginx vhost + PHP-FPM pool (Laravel/WordPress/generic) + directory + auto IPv6 |
| **`/site ssl <domain>`** | Let's Encrypt certificate + auto-renewal (certbot.timer) |
| **`/site list`** | Semua site + SSL status dari database |
| **`/site remove <domain>`** | Hapus Nginx vhost; **data direktori tetap aman** |
| **`/site wizard`** | Interactive step-by-step: domain → framework → DB → OTP confirm |

### Keamanan & Firewall

| Fitur | Deskripsi |
|---|---|
| **`/security [audit\|report\|harden\|ssh-port <port>]`** | Unified security command group (alias: `/security_report`, `/harden`, `/harden_ssh_port`) |
| **`/security audit`** | Audit komprehensif: SSH config, root login status, Fail2Ban, UFW, pending updates, recent logins |
| **`/security report`** | AI analysis auth.log + Fail2Ban → laporan ancaman eksekutif |
| **`/security harden`** | 4-step hardening: SSH self-healing + Fail2Ban setup + UFW baseline + auto-update |
| **`/security ssh-port <port>`** | Ganti port SSH dengan 5-layer safety check (validate → UFW → config → sshd-test → verify) |
| **`/fw [status\|allow\|deny\|rules] [port]`** | UFW management; `/firewall` alias untuk `/fw status` |

### Backup & Recovery

| Fitur | Deskripsi |
|---|---|
| **`/backup [db\|files\|list]`** | Full backup (MySQL dump + web files tar) atau partial (database only atau files only) |
| **`/backup list`** | Daftar 20 backup terbaru (ukuran, tanggal) |
| **`/restore <file>`** | Pulihkan dari `.sql.gz` atau `.tar.gz` (path-traversal protected, OTP) |

### AI Brain & Personalisasi

| Fitur | Deskripsi |
|---|---|
| **`/ai [perintah bebas]`** | Natural language command routing → Claude AI picks action OR multi-step plan (autopilot) |
| **`/cron [jadwal bebas]`** | Parse natural language cron schedule; create systemd timer atau crontab entry |
| **`/token`** | Token usage stats + biaya API riil (USD / IDR) |
| **`/model [haiku\|sonnet\|opus]`** | View / switch AI model (default: Haiku 4.5, Rp ~3/hari; upgradeable ke Sonnet/Opus) |
| **`/optimize`** | Analisis tren metrics 7 hari → AI rekomendasi tuning LEMP (MySQL pool size, Nginx worker, PHP memory limit, dst) |

### Pre-Emptive Firewall (PeFi) — AI-Driven Threat Detection

| Fitur | Deskripsi |
|---|---|
| **`/pefi threats`** | Daftar ancaman terdeteksi (IP, rule, confidence, waktu) |
| **`/pefi rules`** | UFW rules yang aktif sekarang (nomor, port, action) |
| **`/pefi report`** | AI summary threat landscape (common attack vectors, mitigations) |
| **`/pefi health`** | Status sistem PeFi + rule count + last scan + memory usage |
| **`/pefi scan`** | Trigger manual scan sekarang (OTP) |
| **`/pefi block <ip> [jam]`** | Block single IP untuk N jam (backup rule, OTP) |
| **`/pefi unblock <ip>`** | Remove manual block (OTP) |
| **`/pefi whitelist <ip>`** | IP trusted (tidak pernah diblokir, OTP) |
| **`/pefi ignore <threat_id>`** | Mark false positive; AI learns untuk future detection |
| **`/pefi autoblock [on\|off]`** | Enable auto-block HIGH/CRITICAL threats (confidence ≥95%, OTP) |

---

## Value Proposition Ringkas

| Metrik | SyamAdmin | Panel (cPanel/Plesk) | Manual SSH |
|---|---|---|---|
| **Setup time** | 2 menit (chat) | 30 menit (panel + wizard) | 2+ jam (terminal) |
| **Cost/month** | ~Rp 1.000 (API) | Rp 50–200.000 lisensi | Rp 500–2.000.000 gaji sysadmin |
| **Monitoring alerts** | Real-time 24/7 (Telegram) | Cukup baik | Manual SSH polling |
| **Self-update** | ✅ Dari GitHub (`/update`) | ❌ Manual upgrade | ❌ Manual SSH upgrade |
| **AI troubleshooting** | ✅ Diagnose + fix auto | ❌ Need external support | ❌ Manual debugging |
| **Language** | 🇮🇩 100% Indonesian | 🇬🇧 English only | 🇬🇧 English docs |
| **Learning curve** | Chat (sudah familiar) | Web panel (new) | Linux commands (steep) |
| **Audit trail** | ✅ Full SQLite audit log | ✅ Panel logs | ✅ Bash history |

---

## Siapa yang Cocok Menggunakan SyamAdmin?

✅ **Perfect fit:**
- Startup / agency kecil (1–3 engineer, belum punya dedicated sysadmin)
- Co-founders / business owner (non-technical) yang perlu kelola server
- Developer yang lelah SSH-ing atau setup panel
- Tim yang ingin monitoring + respond cepat tanpa on-call stress

❌ **Less ideal:**
- Fortune 500 dengan Tim ops besar (suda ada Kubernetes + Terraform)
- Kebutuhan compliance ketat (audit proprietary, air-gapped network)
- Multiregion/multincloud (saat ini single-server Ubuntu 22.04)

---

## Instalasi & ROI

**Instalasi:** One-click tarball, 2 menit (`bash install.sh`)  
**API Cost:** ~Rp 500–3.000/hari tergantung volume chat & AI requests  
**Payback period:** Kurang dari 1 hari vs hiring sysadmin freelance

```
Skenario: Startup dengan 1 VPS produksi

Sebelum SyamAdmin:
  - Bayar freelancer Rp 500.000–1.000.000 setup: 1×
  - Bayar Rp 100.000–200.000/minggu monitoring/ad-hoc support
  - 1 jam/minggu debugging SSH via terminal

Dengan SyamAdmin (bulan pertama):
  - Install Rp 0 (open source)
  - Chat Rp 1.000–2.000/hari = Rp 30.000–60.000/bulan
  - 5 menit/hari chat (tidak perlu terminal atau SSH)
  
Penghematan bulan 1: Rp 500.000 - 200.000 = Rp 300.000+
ROI: Positif sejak hari ke-2
```

---

## Teknologi di Balik Layar

- **AI Engine**: Claude API (native tool-use, prompt caching, $0.03/hari)
- **Hosting**: Direct di Ubuntu VPS (tidak ada cloud middleware)
- **Database**: SQLite (WAL mode untuk concurrent read/write 3 async tasks)
- **Automation**: asyncio + systemd + cron
- **Monitoring**: Metrics loop 60s + threshold alerts
- **Threat AI**: Pre-Emptive Firewall (rule-based + Claude anomaly analysis)
- **Language**: 100% Bahasa Indonesia (prompts, responses, UI)

---

## Roadmap & Visi

**v3.1 (Saat ini)**
- ✅ Core LEMP provisioning & site management
- ✅ OTP dual-layer security model
- ✅ Memory Core (4 pilar: audit, prefs, history, long-term lessons)
- ✅ Self-update dari GitHub (`/update check/now`)
- ✅ Pre-Emptive Firewall (rule + AI threat detection)
- ✅ Profil admin + konteks waktu sistem
- ✅ 30+ slash commands (registry-driven, konsisten)

**v3.2 (Rencana)**
- [ ] Multi-server management (orchestrate 5+ VPS dari satu chat)
- [ ] Backup cloud integration (S3, Google Cloud Storage)
- [ ] Database snapshot management (MySQL point-in-time recovery)
- [ ] Custom webhook alerts (Slack, Discord, Matrix)
- [ ] API endpoint self-serve (untuk integrasi pihak ketiga)

---

## Support & Komunitas

- **GitHub**: [github.com/Syamsuddin/SyamAdmin](https://github.com/Syamsuddin/SyamAdmin) — open source (MIT license)
- **Issues & Discussion**: GitHub Discussions untuk Q&A & feature requests
- **Docs**: README lengkap + USER_GUIDE + CLAUDE.md (architecture)
- **License**: MIT — fork, modify, deploy tanpa batasan

---

**SyamAdmin: Sysadmin yang bisa Anda ajak chat. Tanpa terminal. Tanpa stress.**
