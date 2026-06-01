# Panduan Migrasi: Pre-v3.1 → v3.2+ (Manual Update)

**Untuk:** Admin SyamAdmin yang running versi lama (sebelum self-updater ada)  
**Tujuan:** Upgrade ke v3.2+ dengan aman, keeping config & database, zero data loss

> **Note:** Setelah upgrade ke v3.2+, Anda bisa gunakan `/update` command di dalam Telegram untuk upgrade berikutnya (fully automated, detached, auto-rollback).

---

## Persiapan (5-10 menit)

### 1. Verifikasi Versi Saat Ini

SSH ke VPS terlebih dahulu:

```bash
ssh root@YOUR_IP
```

Cek versi lama (mungkin tidak ada file VERSION, atau dalam README):

```bash
cat /opt/syamadmin/VERSION 2>/dev/null || echo "Tidak ada VERSION file (v3.0 atau lebih lama)"
```

Catat versi saat ini (mis. "v3.0", "v2.9", atau tidak tahu).

### 2. Backup Database & Config (PENTING!)

**Jangan skip langkah ini.** Ini adalah asuransi Anda.

```bash
# Backup konfigurasi
sudo cp -v /etc/syamadmin/config.env /etc/syamadmin/config.env.backup

# Backup database SQLite
sudo cp -v /var/lib/syamadmin/syamadmin.db /var/lib/syamadmin/syamadmin.db.backup

# Backup installed source code (jaga-jaga)
sudo tar czf /tmp/syamadmin_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  -C /opt syamadmin/ \
  --exclude='syamadmin/venv' \
  --exclude='syamadmin/__pycache__' \
  2>/dev/null && echo "✅ Backup source created"

# List backups yang sudah dibuat
ls -lh /etc/syamadmin/*.backup /var/lib/syamadmin/*.backup /tmp/syamadmin_backup_*.tar.gz 2>/dev/null | tail -5
```

**Jika ada error permission, gunakan sudo.**

### 3. Stop Service (Siapkan Maintenance Window)

```bash
sudo systemctl stop syamadmin
sudo systemctl status syamadmin  # Verifikasi sudah stop (should show "inactive")
```

> **Tip:** Hubungi admin Telegram bahwa server akan down 5-10 menit untuk update.

---

## Upgrade Process (10-15 menit)

### 4. Download v3.2+ Tarball dari GitHub

**Option A: Download dari release GitHub (Recommended)**

```bash
cd /tmp

# Set version yang mau di-download
VERSION="v3.2"  # Atau v3.1, atau latest

# Download tarball dari GitHub releases
wget -q "https://github.com/Syamsuddin/SyamAdmin/archive/refs/tags/${VERSION}.tar.gz" \
  -O "syamadmin_${VERSION}.tar.gz"

# Verify file berhasil download
ls -lh syamadmin_${VERSION}.tar.gz
```

**Option B: Download dari branch `main` (latest development)**

```bash
cd /tmp
wget -q "https://github.com/Syamsuddin/SyamAdmin/archive/refs/heads/main.tar.gz" \
  -O "syamadmin_main.tar.gz"
ls -lh syamadmin_main.tar.gz
```

### 5. Extract & Validate Structure

```bash
cd /tmp

# Extract tarball
tar xzf syamadmin_${VERSION}.tar.gz 2>/dev/null || tar xzf syamadmin_main.tar.gz
ls -d SyamAdmin-* | head -1

# Verifikasi struktur lengkap (harus ada file-file ini)
EXTRACT_DIR=$(ls -d SyamAdmin-* | head -1)
echo "✓ Checking structure in $EXTRACT_DIR:"
test -f "$EXTRACT_DIR/syamadmin.py" && echo "  ✓ syamadmin.py" || echo "  ✗ syamadmin.py MISSING"
test -f "$EXTRACT_DIR/VERSION" && echo "  ✓ VERSION" || echo "  ⚠ VERSION (tidak ada di versi lama, oke)"
test -d "$EXTRACT_DIR/modules" && echo "  ✓ modules/" || echo "  ✗ modules/ MISSING"
test -d "$EXTRACT_DIR/scripts" && echo "  ✓ scripts/" || echo "  ✗ scripts/ MISSING"
test -d "$EXTRACT_DIR/templates" && echo "  ✓ templates/" || echo "  ✗ templates/ MISSING"
```

### 6. Backup Current Installation

```bash
# Create dated backup dari current /opt/syamadmin
BACKUP_TS=$(date +%Y%m%d_%H%M%S)
sudo cp -a /opt/syamadmin "/opt/syamadmin.${BACKUP_TS}.backup"
echo "✅ Backup created: /opt/syamadmin.${BACKUP_TS}.backup"

# Verify backup
sudo ls -ld /opt/syamadmin.*.backup | tail -3
```

### 7. Replace Application Files (Keep venv, config, database)

```bash
# Pastikan sudah di /tmp/SyamAdmin-XXX directory
cd /tmp
EXTRACT_DIR=$(ls -d SyamAdmin-* | head -1)
cd "$EXTRACT_DIR"

# Copy source files (kecuali venv, db, config - mereka sudah di /opt/)
echo "Copying new application files..."
sudo cp -v syamadmin.py /opt/syamadmin/
sudo cp -v VERSION /opt/syamadmin/ 2>/dev/null || echo "⚠ VERSION file tidak ada (OK jika v3.0)"
sudo cp -v requirements.txt /opt/syamadmin/ 2>/dev/null || echo "⚠ requirements.txt tidak ada"
sudo cp -rv modules/ /opt/syamadmin/
sudo cp -rv templates/ /opt/syamadmin/
sudo cp -rv scripts/ /opt/syamadmin/

# Fix permissions
sudo chown -R root:root /opt/syamadmin/
sudo chmod +x /opt/syamadmin/scripts/*.sh
echo "✅ Files copied"
```

**Penting:** Verify bahwa `/opt/syamadmin/venv` masih ada & tidak tersentuh:

```bash
ls -ld /opt/syamadmin/venv
```

### 8. Update Python Dependencies (jika ada requirements.txt)

```bash
# Aktivasi venv
source /opt/syamadmin/venv/bin/activate

# Upgrade pip terlebih dahulu
pip install --upgrade pip

# Install/upgrade packages
if [ -f /opt/syamadmin/requirements.txt ]; then
  pip install -q -r /opt/syamadmin/requirements.txt
  echo "✅ Dependencies updated"
else
  echo "⚠ requirements.txt tidak ditemukan (mungkin v3.0) — skip pip update"
fi

# Deactivate venv
deactivate
```

### 9. Start Service & Verify

```bash
# Start service
sudo systemctl start syamadmin

# Wait 3 detik biar process stabil
sleep 3

# Check status
sudo systemctl status syamadmin
```

**Harus keluar `active (running)`. Jika error, lihat [Troubleshooting](#troubleshooting) di bawah.**

### 10. Verify dari Telegram

Di bot Telegram Anda, kirim:

```
/start
```

Harus mendapat reply:
```
🤖 SyamAdmin Agent
Server: vps-xxx
Status: 🟢 Online
```

Lalu kirim:

```
/status
```

Harus keluar dashboard lengkap dengan versi (jika ada) di bagian atas.

### 11. Test Beberapa Fitur Dasar

```
/help           → Harus keluar daftar command
/audit          → Harus keluar riwayat command (mungkin kosong di first run)
/logs           → Harus keluar log file (atau "tidak ada log")
```

---

## Rollback (Jika Ada Error)

**Jika ada masalah, rollback ke backup:**

### Option A: Restore dari Backup Dated

```bash
# List available backups
sudo ls -ld /opt/syamadmin.*.backup

# Restore (ganti TIMESTAMP dengan tanggal backup)
sudo rm -rf /opt/syamadmin
sudo mv /opt/syamadmin.YYYYMMDD_HHMMSS.backup /opt/syamadmin
sudo systemctl start syamadmin
```

### Option B: Restore Hanya Source, Keeping Config & DB

```bash
# Restore hanya file .py & modules (config & db otomatis preserved)
BACKUP_TS="YYYYMMDD_HHMMSS"  # Set ke tanggal backup
sudo rm -rf /opt/syamadmin/{syamadmin.py,modules,templates,scripts}
sudo cp -a /opt/syamadmin.${BACKUP_TS}.backup/{syamadmin.py,modules,templates,scripts} /opt/syamadmin/

# Restart
sudo systemctl restart syamadmin
```

---

## Troubleshooting

### Q: Service tidak bisa start (`systemctl status` menunjukkan error)

**A:** Cek log:

```bash
sudo journalctl -u syamadmin -n 50 --no-pager
```

**Kemungkinan:**
- Module tidak ditemukan → Pastikan file `modules/` di-copy dengan benar
- Python syntax error → Rollback ke backup (mungkin corruption saat download)
- Import error (missing package) → Run `pip install -r requirements.txt` lagi

### Q: Bot tidak merespons `/start`

**A:** Service sedang mati atau terjadi crash:

```bash
# Check process
ps aux | grep syamadmin | grep -v grep

# Check recent errors
sudo journalctl -u syamadmin -n 20 --no-pager | tail

# Restart
sudo systemctl restart syamadmin
sleep 5
sudo systemctl status syamadmin
```

### Q: Database error setelah upgrade

**A:** Mungkin schema lama tidak compatible. Restore database:

```bash
sudo rm /var/lib/syamadmin/syamadmin.db
sudo systemctl restart syamadmin
# Service akan auto-create schema baru saat startup
```

> **Warning:** Ini akan menghapus semua audit log & chat history lama. Jika critical, restore dari backup terlebih dahulu.

### Q: "Module not found" error

**A:** Verifikasi struktur:

```bash
ls -la /opt/syamadmin/modules/ | head -10
```

Harus ada file: `brain.py`, `executor.py`, `telegram_bot.py`, dll.

Jika kosong, re-copy dari extract directory:

```bash
cd /tmp/SyamAdmin-*/
sudo cp -rv modules/ /opt/syamadmin/
```

---

## Setelah Upgrade Berhasil

### Langkah Selanjutnya

1. **Cek** semua fitur utama di Telegram
2. **Monitor** logs untuk errors:
   ```bash
   sudo journalctl -u syamadmin -f  # Real-time log tail
   ```
3. **Test AI commands** (jika ada `ANTHROPIC_API_KEY`):
   ```
   /ai restart nginx
   ```
4. **Sekarang bisa** gunakan `/update` untuk upgrade ke versi lebih baru!

### Fitur Baru di v3.1+

Setelah upgrade, Anda sekarang punya:

- ✅ `/update` — auto-check & install update dari GitHub
- ✅ `/profile` — setup admin profil & konteks server
- ✅ `/service` — direct systemctl control (restart/stop/start layanan)
- ✅ Enriched `/logs` — bisa pilih layanan specific + custom line count
- ✅ `/sysupdate` — apt-get update & upgrade (rename dari `/update` lama)
- ✅ **Profile context** — AI tahu nama admin, zona waktu, hobi (lebih personal)
- ✅ **System time context** — AI aware pukul berapa sekarang (salam: pagi/siang/sore/malam)

---

## Upgrade ke Versi Lebih Baru (Setelah v3.1+)

Setelah berhasil upgrade ke v3.1+, upgrade berikutnya **JAUH lebih mudah:**

```
1. (Di Telegram) /update check
   → "v3.1 ada, v3.2 tersedia"

2. /update now + OTP
   → Bot otomatis:
      - Backup
      - Download dari GitHub
      - Swap file
      - Restart service
      - Health-check
      - Notify hasil

3. Done!
```

Tidak perlu SSH lagi untuk upgrade. Semua dari Telegram. 🚀

---

## Checklist Akhir

- [ ] Sudah backup config.env & syamadmin.db
- [ ] Sudah backup /opt/syamadmin source
- [ ] Sudah extract tarball dan verify struktur
- [ ] Sudah stop service sebelum replace file
- [ ] Sudah copy file & run pip install -r requirements.txt
- [ ] Service bisa start (systemctl status = active)
- [ ] Bot respond ke /start dan /status di Telegram
- [ ] Testing fitur dasar (/help, /logs, /audit)
- [ ] Documentation udah di-update (README, CLAUDE.md)

**Jika semua ✅, upgrade sukses!**

---

## Support & Rollback SOP

| Scenario | Action | Waktu |
|----------|--------|-------|
| Service mati setelah upgrade | Restore backup dated, restart | 2 menit |
| Database corrupt | Delete .db file, let app recreate | 1 menit |
| Missing module | Re-copy modules/ dari extract dir | 1 menit |
| Rollback penuh (ke versi lama) | `sudo mv syamadmin.YYYYMMDD.backup syamadmin`, restart | 2 menit |

---

**Happy upgrading! 🎉**

Jika ada masalah, cek logs dan baca Troubleshooting di atas. Atau buka issue di GitHub: https://github.com/Syamsuddin/SyamAdmin/issues
