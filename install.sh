#!/usr/bin/env bash
# ============================================================
# SyamAdmin Installer — Ubuntu 22.04 LTS
# One-click install: dependencies, venv, systemd service
# ============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="/opt/syamadmin"
CONFIG_DIR="/etc/syamadmin"
LOG_DIR="/var/log/syamadmin"
DATA_DIR="/var/lib/syamadmin"
VENV_DIR="${INSTALL_DIR}/venv"

banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════╗"
    echo "║     🤖 SyamAdmin Agent Installer         ║"
    echo "║     AI-Powered Sysadmin for Ubuntu       ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Script harus dijalankan sebagai root (sudo)"
        exit 1
    fi
}

check_os() {
    if ! grep -q "Ubuntu 22.04\|Ubuntu 24.04" /etc/os-release 2>/dev/null; then
        log_warn "OS bukan Ubuntu 22.04/24.04. Lanjut dengan risiko sendiri."
        read -p "Lanjutkan? (y/n): " -n 1 -r
        echo
        [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
    fi
    log_info "OS: $(lsb_release -ds)"
}

install_system_deps() {
    log_info "Mengupdate package list..."
    apt-get update -qq

    log_info "Menginstall system dependencies..."
    apt-get install -y -qq \
        python3 python3-pip python3-venv \
        curl wget git unzip jq \
        sqlite3 \
        htop iotop nethogs \
        rkhunter lynis \
        cron logrotate \
        > /dev/null 2>&1

    log_info "System dependencies terinstall."
}

setup_directories() {
    log_info "Membuat direktori..."
    mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}" "${LOG_DIR}" "${DATA_DIR}"
    chmod 750 "${CONFIG_DIR}"
    chmod 755 "${LOG_DIR}" "${DATA_DIR}"
}

copy_files() {
    log_info "Menyalin file agent..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp -r "${SCRIPT_DIR}/syamadmin.py" "${INSTALL_DIR}/"
    cp -r "${SCRIPT_DIR}/modules" "${INSTALL_DIR}/"
    cp -r "${SCRIPT_DIR}/templates" "${INSTALL_DIR}/"
    cp -r "${SCRIPT_DIR}/scripts" "${INSTALL_DIR}/"
    chmod +x "${INSTALL_DIR}/scripts/"*.sh 2>/dev/null || true

    if [[ ! -f "${CONFIG_DIR}/config.env" ]]; then
        cp "${SCRIPT_DIR}/config.env.example" "${CONFIG_DIR}/config.env"
        chmod 600 "${CONFIG_DIR}/config.env"
        log_warn "Config disalin ke ${CONFIG_DIR}/config.env — EDIT SEBELUM MENJALANKAN!"
    else
        log_info "Config sudah ada, tidak di-overwrite."
    fi
}

setup_venv() {
    log_info "Membuat Python virtual environment..."
    python3 -m venv "${VENV_DIR}"

    log_info "Menginstall Python dependencies..."
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet \
        python-telegram-bot==21.* \
        anthropic==0.* \
        aiohttp \
        psutil \
        aiosqlite \
        python-dotenv \
        jinja2 \
        croniter \
        httpx

    log_info "Python dependencies terinstall."
}

setup_systemd() {
    log_info "Mengkonfigurasi systemd service..."
    cat > /etc/systemd/system/syamadmin.service << 'UNIT'
[Unit]
Description=SyamAdmin AI Sysadmin Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/syamadmin
EnvironmentFile=/etc/syamadmin/config.env
ExecStart=/opt/syamadmin/venv/bin/python3 /opt/syamadmin/syamadmin.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/syamadmin/agent.log
StandardError=append:/var/log/syamadmin/agent.log

# Service berjalan sebagai root dan perlu akses penuh ke /root (misal .my.cnf)
NoNewPrivileges=false
ProtectHome=no

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    log_info "Systemd service terkonfigurasi."
}

setup_logrotate() {
    log_info "Mengkonfigurasi logrotate..."
    cat > /etc/logrotate.d/syamadmin << 'LOGROTATE'
/var/log/syamadmin/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        systemctl reload syamadmin > /dev/null 2>&1 || true
    endscript
}
LOGROTATE
}

setup_database() {
    log_info "Menginisialisasi database..."
    "${VENV_DIR}/bin/python3" -c "
import sqlite3, os
db = sqlite3.connect('${DATA_DIR}/syamadmin.db')
c = db.cursor()
c.executescript('''
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    user_id TEXT,
    status TEXT DEFAULT \"success\"
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL,
    metadata TEXT
);
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT UNIQUE NOT NULL,
    root_path TEXT NOT NULL,
    php_version TEXT DEFAULT \"8.3\",
    ssl_enabled INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT \"active\"
);
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    schedule TEXT NOT NULL,
    config TEXT,
    enabled INTEGER DEFAULT 1,
    last_run DATETIME,
    next_run DATETIME
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    severity TEXT NOT NULL,
    module TEXT NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp, metric_type);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(timestamp, severity);
''')
db.commit()
db.close()
print('Database initialized.')
"
}

print_next_steps() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  ✅ SyamAdmin berhasil diinstall!                ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Langkah selanjutnya:${NC}"
    echo ""
    echo "  1. Edit konfigurasi:"
    echo -e "     ${GREEN}sudo nano /etc/syamadmin/config.env${NC}"
    echo ""
    echo "  2. Set Telegram Bot Token & Admin ID"
    echo "     - Buat bot via @BotFather di Telegram"
    echo "     - Dapatkan User ID via @userinfobot"
    echo ""
    echo "  3. Set Anthropic API Key"
    echo "     - Dari https://console.anthropic.com/"
    echo ""
    echo "  4. Jalankan agent:"
    echo -e "     ${GREEN}sudo systemctl enable --now syamadmin${NC}"
    echo ""
    echo "  5. Cek status:"
    echo -e "     ${GREEN}sudo systemctl status syamadmin${NC}"
    echo -e "     ${GREEN}sudo journalctl -u syamadmin -f${NC}"
    echo ""
    echo "  6. Buka Telegram, kirim /start ke bot Anda"
    echo ""
}

# === Main ===
banner
check_root
check_os
install_system_deps
setup_directories
copy_files
setup_venv
setup_systemd
setup_logrotate
setup_database
print_next_steps
