# Panduan Fresh Install SyamAdmin v3.2

**Untuk:** Admin baru yang akan install SyamAdmin v3.2 dari GitHub ke VPS Ubuntu 22.04 baru  
**Waktu total:** 30-45 menit (termasuk konfigurasi)  
**Hasil:** SyamAdmin daemon running di VPS, controllable via Telegram

> **Prerequisites:** VPS Ubuntu 22.04 LTS dengan akses root + internet connection

---

## Phase 1: Persiapan Akun & Token (10 menit)

### Langkah 1: Buat Telegram Bot

Telegram bot diperlukan agar SyamAdmin bisa mengirim pesan & menerima command dari Anda.

1. **Buka Telegram**, cari **@BotFather**
2. Kirim `/start`
3. Kirim `/newbot`
4. BotFather tanya: **"Berikan nama untuk bot baru Anda"**
   - Jawab contoh: `SyamAdmin VPS` (bisa custom)
5. BotFather tanya: **"Atur username untuk bot Anda"**
   - Username harus diakhiri `bot`, contoh: `syamadmin_vps_bot`
6. BotFather akan reply dengan token berformat:
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```
   **Simpan token ini** — akan dibutuhkan di step konfigurasi.

### Langkah 2: Dapatkan Telegram User ID Anda

1. **Buka Telegram**, cari **@userinfobot**
2. Kirim message apa pun (mis. `/start` atau `hi`)
3. Bot akan membalas info Anda termasuk **Id: 123456789**
   - **Catat angka Id ini** — bukan username, tapi angka user ID.

### Langkah 3: (Opsional) Ambil Anthropic API Key untuk AI Features

Jika ingin menggunakan fitur AI Brain (`/ai`, `/optimize`, `/cron`, `/security report`):

1. Buka https://console.anthropic.com
2. Login atau register (gratis)
3. Ke **API Keys** section
4. Click **Create Key**
5. Copy key (berformat `sk-ant-xxx...`)
   - **Simpan key ini** — akan dibutuhkan di konfigurasi.

> **Note:** Tanpa API key, SyamAdmin masih bisa digunakan, tapi command AI hanya pake keyword parser sederhana (tidak cerdas). Dengan API key: full AI power, biaya ~Rp 500–3000/hari tergantung usage.

---

## Phase 2: Server Setup & Installation (20-30 menit)

### Langkah 4: SSH ke VPS & Verifikasi OS

```bash
# SSH ke server Anda
ssh root@YOUR_VPS_IP
# Atau jika menggunakan custom SSH key:
# ssh -i /path/to/key.pem root@YOUR_VPS_IP
```

Verifikasi OS:

```bash
cat /etc/os-release | grep PRETTY_NAME
# Harus output: Ubuntu 22.04 LTS (atau 24.04 juga oke)
```

### Langkah 5: Download SyamAdmin v3.2 dari GitHub

```bash
cd /tmp

# Download tarball dari GitHub release (v3.2)
wget -q "https://github.com/Syamsuddin/SyamAdmin/archive/refs/tags/v3.2.tar.gz" \
  -O "syamadmin_v3.2.tar.gz"

# Atau jika v3.2 belum ada, download dari main branch (latest):
# wget -q "https://github.com/Syamsuddin/SyamAdmin/archive/refs/heads/main.tar.gz" \
#   -O "syamadmin_main.tar.gz"

# Verifikasi file berhasil didownload
ls -lh syamadmin_*.tar.gz
```

### Langkah 6: Extract & Verify Struktur

```bash
# Extract tarball
tar xzf syamadmin_v3.2.tar.gz

# Cek folder yang ter-extract
ls -d SyamAdmin-* | head -1
EXTRACT_DIR=$(ls -d SyamAdmin-* | head -1)

# Verifikasi file penting ada
echo "Checking structure:"
test -f "$EXTRACT_DIR/syamadmin.py" && echo "✓ syamadmin.py" || echo "✗ MISSING"
test -f "$EXTRACT_DIR/install.sh" && echo "✓ install.sh" || echo "✗ MISSING"
test -f "$EXTRACT_DIR/config.env.example" && echo "✓ config.env.example" || echo "✗ MISSING"
test -d "$EXTRACT_DIR/modules" && echo "✓ modules/" || echo "✗ MISSING"
test -d "$EXTRACT_DIR/scripts" && echo "✓ scripts/" || echo "✗ MISSING"

# Jika semua ✓, lanjut ke step 7
```

### Langkah 7: Run Installer

```bash
cd "$EXTRACT_DIR"

# Lihat apa yang akan installer lakukan
head -50 install.sh

# Run installer (akan minta password sudo)
chmod +x install.sh
sudo ./install.sh
```

**Installer akan:**
1. ✅ Install dependencies (Python, curl, git, sqlite3, etc)
2. ✅ Buat directory structure (`/opt/syamadmin`, `/etc/syamadmin`, `/var/lib/syamadmin`, dll)
3. ✅ Create Python virtual environment
4. ✅ Install Python packages (telegram-bot, anthropic, psutil, dll)
5. ✅ Setup systemd service `syamadmin` (auto-start saat boot)
6. ✅ Initialize database SQLite

**Durasi:** 3-10 menit (tergantung internet speed)

Output harus berakhir dengan:
```
✓ SyamAdmin installation complete!
✓ Start: sudo systemctl enable --now syamadmin
✓ Status: sudo systemctl status syamadmin
```

---

## Phase 3: Konfigurasi (5-10 menit)

### Langkah 8: Edit Konfigurasi

```bash
# Edit config file dengan nano atau vi
sudo nano /etc/syamadmin/config.env
```

**File yang muncul adalah template.** Edit bagian ini:

```env
# WAJIB diisi:
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_ID=987654321

# SANGAT DISARANKAN:
ANTHROPIC_API_KEY=sk-ant-xxxxx
SERVER_NAME=vps-ku-01

# OPSIONAL (bisa pakai default):
SERVER_TIMEZONE=Asia/Jakarta
```

**Petunjuk edit di nano:**
- Gunakan arrow keys untuk navigate
- Type untuk edit
- `Ctrl+O` lalu Enter untuk save
- `Ctrl+X` untuk exit

**Dari mana ambil nilainya:**
- `TELEGRAM_BOT_TOKEN` → Token dari @BotFather (Langkah 1)
- `TELEGRAM_ADMIN_ID` → Angka Id dari @userinfobot (Langkah 2)
- `ANTHROPIC_API_KEY` → (Opsional) Dari console.anthropic.com (Langkah 3)
- `SERVER_NAME` → Nama identitas VPS (bebas, mis. "vps-nustek-01")
- `SERVER_TIMEZONE` → IANA timezone (mis. "Asia/Jakarta", "Asia/Makassar", "UTC")

**Contoh hasil edit:**

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_ID=987654321
ANTHROPIC_API_KEY=sk-ant-v7-xxxxx
SERVER_NAME=nustek-vps-01
SERVER_TIMEZONE=Asia/Jakarta
CLAUDE_MODEL=claude-haiku-4-5-20251001
ALERT_THRESHOLD_CPU=85
ALERT_THRESHOLD_RAM=90
ALERT_THRESHOLD_DISK=85
```

Save & exit.

### Langkah 9: Start Service

```bash
# Enable auto-start saat boot + start sekarang
sudo systemctl enable --now syamadmin

# Verifikasi status
sudo systemctl status syamadmin
```

Output harus keluar:
```
● syamadmin.service - SyamAdmin AI Sysadmin Agent
   Loaded: loaded (/etc/systemd/system/syamadmin.service; enabled; ...)
   Active: active (running) since ... 
```

Jika melihat `active (running)` ✓ berarti berhasil!

Tekan `Q` untuk exit status view.

---

## Phase 4: Verifikasi & First Setup (5-10 menit)

### Langkah 10: Test Bot di Telegram

Buka **Telegram**, cari bot yang Anda buat (dari Langkah 1, username-nya).

Kirim `/start`:

```
Harusnya bot reply:
🤖 SyamAdmin Agent
Server: nustek-vps-01
Status: 🟢 Online

Kirim /help untuk daftar perintah.
```

Jika **tidak ada reply**, cek troubleshooting di bawah.

### Langkah 11: Lihat Dashboard

Kirim `/status`:

Output harus lengkap: CPU, RAM, Disk, uptime, IP address, services status, dll.

### Langkah 12: Setup Admin Profile (Opsional tapi Disarankan)

Kirim `/profile setup`:

Bot akan tanya step-by-step:
- Nama lengkap Anda
- Panggilan kesukaan (nickname)
- Pekerjaan
- Lokasi
- Timezone
- Hobi
- Gaya komunikasi (santai/formal/ringkas)

Jawab setiap pertanyaan dengan mengetik & kirim. Bisa `lewati` untuk opsional.

**Benefit:** Setelah setup, AI akan menyapa Anda dengan nama & paham konteks (timezone, jam lokal, gaya komunikasi).

### Langkah 13: Test Beberapa Command

```
/help           → Daftar lengkap command
/logs           → Lihat log terbaru
/audit          → Lihat riwayat command
/ai hi          → Test AI (jika punya API key)
```

Semua harus respond tanpa error.

---

## Phase 5: Next Steps & Learning

### Langkah 14: Backup Config & Database (Opsional tapi PENTING)

Jika sudah stabil 24 jam, backup supaya aman:

```bash
# Backup config
sudo cp /etc/syamadmin/config.env /etc/syamadmin/config.env.backup

# Backup database
sudo cp /var/lib/syamadmin/syamadmin.db /var/lib/syamadmin/syamadmin.db.backup

# Verify
ls -lh /etc/syamadmin/*.backup /var/lib/syamadmin/*.backup
```

### Langkah 15: Monitor Logs (Opsional)

Untuk melihat live log daemon:

```bash
# Real-time log tail (Ctrl+C untuk stop)
sudo journalctl -u syamadmin -f
```

Harus keluar log-log tanpa error. Misal:
```
[syamadmin.bot] INFO: Command /status from admin
[syamadmin.monitor] INFO: CPU 15%, RAM 30%, Disk 45%
```

---

## Troubleshooting

### ❌ Bot tidak merespons `/start`

**Diagnosis:**

```bash
# Cek apakah service sedang running
sudo systemctl status syamadmin

# Cek log untuk error
sudo journalctl -u syamadmin -n 20 --no-pager
```

**Solusi:**
- **Jika status: inactive** → Run: `sudo systemctl restart syamadmin`
- **Jika ada error di log** → Baca error message, kemungkinan:
  - Config file salah (typo di token)
  - Internet tidak connected
  - Token Telegram invalid (copy ulang dari BotFather)

### ❌ "ModuleNotFoundError: No module named..."

Berarti pip packages tidak terinstall dengan benar.

```bash
# Manual install
source /opt/syamadmin/venv/bin/activate
pip install -q -r /opt/syamadmin/requirements.txt
deactivate

# Restart service
sudo systemctl restart syamadmin
```

### ❌ "Permission denied" saat setup

Selalu gunakan `sudo` untuk command yang touch `/opt`, `/etc/syamadmin`, `/var/lib/syamadmin`:

```bash
# BENAR:
sudo nano /etc/syamadmin/config.env

# SALAH (jangan):
nano /etc/syamadmin/config.env
```

### ❌ Installer error di `pip install`

Mungkin internet timeout. Re-run:

```bash
cd /tmp/SyamAdmin-*/
sudo ./install.sh
```

Jika berulang, coba:

```bash
# Clear pip cache
pip cache purge

# Manual venv setup
python3 -m venv /opt/syamadmin/venv
source /opt/syamadmin/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/syamadmin/requirements.txt
```

---

## Key Commands After Install

```bash
# Start / stop / restart daemon
sudo systemctl restart syamadmin
sudo systemctl stop syamadmin
sudo systemctl start syamadmin

# Check status
sudo systemctl status syamadmin

# View logs
sudo journalctl -u syamadmin -f          # Real-time
sudo tail -f /var/log/syamadmin/agent.log

# Manage config
sudo nano /etc/syamadmin/config.env      # Edit config
sudo systemctl restart syamadmin         # Apply changes

# Backup
sudo cp /var/lib/syamadmin/syamadmin.db /tmp/backup.db
```

---

## Folder Structure Reference

```
VPS installation:
├── /opt/syamadmin/              # Application code + venv
│   ├── venv/                    # Python virtual environment
│   ├── syamadmin.py             # Main daemon
│   ├── VERSION                  # Version file (3.2)
│   ├── modules/                 # Core modules (brain, executor, etc)
│   ├── scripts/                 # Helper scripts (update.sh, etc)
│   ├── templates/               # Nginx/PHP templates
│   └── requirements.txt          # Python dependencies
│
├── /etc/syamadmin/              # Configuration
│   ├── config.env               # Main config (WAJIB isi!)
│   └── config.env.backup        # Backup (Anda buat manual)
│
├── /var/lib/syamadmin/          # Data
│   ├── syamadmin.db             # SQLite database (audit log, metrics, sites)
│   ├── syamadmin.db.backup      # Database backup (Anda buat manual)
│   └── backups/                 # Directory untuk backup site/db
│
└── /var/log/syamadmin/          # Logs
    ├── agent.log                # Application log
    └── update.log               # Self-update log
```

---

## Next: Upgrade ke Versi Terbaru

Setelah install v3.2, untuk upgrade ke versi lebih baru (v3.3, v3.4, dst):

**Di Telegram:**
```
/update check      # Cek ada versi baru
/update now        # Install update (OTP required)
```

**Selesai!** Service auto-backup, download, swap, health-check, notify. Zero downtime. 🚀

---

## Configuration Reference

### Required Parameters

| Param | Description | Example |
|-------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token dari @BotFather | `123456:ABC...` |
| `TELEGRAM_ADMIN_ID` | Telegram user ID Anda | `987654321` |

### Recommended Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `ANTHROPIC_API_KEY` | (kosong) | API key untuk AI features (gratis 1st month, then ~$0.03/day) |
| `SERVER_NAME` | `VPS` | Identitas server di notifikasi |
| `SERVER_TIMEZONE` | `Asia/Jakarta` | Timezone untuk waktu sistem |

### Monitoring Thresholds (opsional)

| Param | Default | Description |
|-------|---------|-------------|
| `ALERT_THRESHOLD_CPU` | `85` | Alert jika CPU > 85% |
| `ALERT_THRESHOLD_RAM` | `90` | Alert jika RAM > 90% |
| `ALERT_THRESHOLD_DISK` | `85` | Alert jika disk > 85% |
| `ALERT_THRESHOLD_LOAD` | `4.0` | Alert jika load avg > 4.0 |
| `MONITOR_INTERVAL` | `60` | Check metrics setiap 60 detik |

---

## Checklist: Fresh Install Complete

- [ ] Telegram bot created (@BotFather)
- [ ] Telegram user ID noted (@userinfobot)
- [ ] (Opsional) Anthropic API key dari console.anthropic.com
- [ ] VPS Ubuntu 22.04 ready (dapat SSH access)
- [ ] Tarball downloaded & extracted
- [ ] Installer run berhasil (systemctl status = active)
- [ ] config.env sudah di-edit dengan token & user ID
- [ ] Bot respond ke `/start` di Telegram
- [ ] Bot respond ke `/status` dengan dashboard lengkap
- [ ] Profile setup done (opsional tapi recommended)
- [ ] Backup config.env & syamadmin.db sudah dibuat

**Jika semua ✅, SyamAdmin v3.2 siap digunakan!** 🎉

---

## Support & Docs

- **Live Log**: `sudo journalctl -u syamadmin -f`
- **Config**: `/etc/syamadmin/config.env`
- **Database**: `/var/lib/syamadmin/syamadmin.db`
- **GitHub**: https://github.com/Syamsuddin/SyamAdmin
- **Issues**: https://github.com/Syamsuddin/SyamAdmin/issues

---

**Happy sysadmining!** 🚀

Selamat datang ke SyamAdmin v3.2 — sysadmin yang bisa Anda ajak chat.
