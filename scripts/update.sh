#!/usr/bin/env bash
# ============================================================
# SyamAdmin Self-Updater (detached, self-healing)
# Dipicu oleh perintah /update via modules/updater.py.
#
# Alur: backup → unduh tarball GitHub → ganti file aplikasi →
#       restart service → health-check → auto-rollback bila gagal.
# Dijalankan TERLEPAS (setsid+nohup) agar selamat saat service
# syamadmin di-restart di tengah proses.
# ============================================================
set -uo pipefail

REPO="Syamsuddin/SyamAdmin"
BRANCH="main"
DIR="/opt/syamadmin"
SERVICE="syamadmin"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)    REPO="$2";    shift 2 ;;
    --branch)  BRANCH="$2";  shift 2 ;;
    --dir)     DIR="$2";     shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

CONFIG="/etc/syamadmin/config.env"
DATA_DIR="/var/lib/syamadmin"
BK_DIR="${DATA_DIR}/backups"
VENV="${DIR}/venv"
TS="$(date +%Y%m%d_%H%M%S)"
BK="${BK_DIR}/syamadmin_${TS}.tar.gz"

log() { echo "[update ${TS}] $*"; }

# Kirim notifikasi Telegram langsung (bot mungkin sedang restart).
notify() {
  local token chat
  token="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$CONFIG" 2>/dev/null | head -1 | cut -d= -f2-)"
  chat="$(grep -E '^TELEGRAM_ADMIN_ID=' "$CONFIG" 2>/dev/null | head -1 | cut -d= -f2-)"
  [[ -z "$token" || -z "$chat" ]] && return 0
  curl -s --max-time 10 "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${chat}" \
    --data-urlencode "text=$1" \
    -d parse_mode=Markdown >/dev/null 2>&1 || true
}

rollback() {
  log "ROLLBACK dari ${BK}"
  if [[ -f "$BK" ]]; then
    tar xzf "$BK" -C "$DIR" 2>/dev/null || log "WARNING: ekstraksi backup bermasalah"
    systemctl restart "$SERVICE" 2>/dev/null || true
  else
    log "WARNING: file backup tidak ada, rollback dilewati"
  fi
}

mkdir -p "$BK_DIR"
OLD_VER="$(cat "${DIR}/VERSION" 2>/dev/null || echo '?')"
log "Mulai update: repo=${REPO} branch=${BRANCH} dir=${DIR} (versi sekarang ${OLD_VER})"

# 1. Backup (kecuali venv, scratch, db, cache, arsip)
log "Backup → ${BK}"
if ! tar czf "$BK" -C "$DIR" \
      --exclude='venv' --exclude='scratch' --exclude='*.db' \
      --exclude='__pycache__' --exclude='*.tar.gz' . 2>/dev/null; then
  log "Backup GAGAL — batalkan update."
  notify "❌ *Update gagal*: proses backup error. Update dibatalkan, sistem tidak berubah."
  exit 1
fi

# 2. Unduh tarball sumber dari GitHub (tanpa git)
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TARURL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"
log "Unduh ${TARURL}"
if ! curl -fsSL --max-time 120 "$TARURL" -o "${TMP}/src.tar.gz"; then
  log "Unduh GAGAL."
  notify "❌ *Update gagal*: unduh dari GitHub error. Sistem tidak berubah."
  exit 1
fi

# 3. Ekstrak
if ! tar xzf "${TMP}/src.tar.gz" -C "$TMP" 2>/dev/null; then
  log "Ekstrak GAGAL."
  notify "❌ *Update gagal*: ekstraksi tarball error. Sistem tidak berubah."
  exit 1
fi
SRC="$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -1)"
if [[ -z "$SRC" || ! -f "${SRC}/syamadmin.py" ]]; then
  log "Struktur tarball tidak valid (syamadmin.py tak ditemukan)."
  notify "❌ *Update gagal*: isi tarball tidak valid. Sistem tidak berubah."
  exit 1
fi
NEW_VER="$(cat "${SRC}/VERSION" 2>/dev/null || echo '?')"
log "Versi baru di tarball: ${NEW_VER}"

# 4. Ganti file aplikasi (tarball bersih: tanpa venv/db/config → cp -a aman,
#    venv & data di luar SRC tidak tersentuh). Tanpa rsync dependency.
log "Menyalin file aplikasi baru"
if ! cp -a "${SRC}/." "${DIR}/" 2>/dev/null; then
  log "Penyalinan GAGAL — rollback."
  rollback
  notify "⚠️ *Update gagal* saat menyalin file. Rollback dijalankan ke \`${OLD_VER}\`."
  exit 1
fi
chmod +x "${DIR}/scripts/"*.sh 2>/dev/null || true

# 5. Update dependencies (bila ada requirements.txt)
if [[ -f "${DIR}/requirements.txt" && -x "${VENV}/bin/pip" ]]; then
  log "pip install -r requirements.txt"
  "${VENV}/bin/pip" install --quiet -r "${DIR}/requirements.txt" 2>/dev/null || log "pip warning (lanjut)"
fi

# 6. Restart service
log "Restart ${SERVICE}"
systemctl restart "$SERVICE" 2>/dev/null || true

# 7. Health-check + auto-rollback
sleep 8
if systemctl is-active --quiet "$SERVICE"; then
  log "OK — service aktif. Update ${OLD_VER} → ${NEW_VER} selesai."
  notify "$(printf '✅ *SyamAdmin ter-update!*\nVersi: `%s` → `%s`\nStatus: 🟢 aktif kembali.' "$OLD_VER" "$NEW_VER")"
else
  log "Service GAGAL aktif setelah update — ROLLBACK."
  rollback
  sleep 5
  if systemctl is-active --quiet "$SERVICE"; then
    notify "$(printf '⚠️ *Update gagal, rollback sukses.*\nVersi tetap `%s`. Cek `/var/log/syamadmin/update.log`.' "$OLD_VER")"
  else
    notify "🚨 *Update gagal & service belum naik!* Perlu pemeriksaan manual. Cek \`/var/log/syamadmin/update.log\`."
  fi
fi
log "Selesai."
