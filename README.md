<p align="center">
  <img src="img/header.jpg" alt="SyamAdmin Header" width="100%">
</p>

<p align="center">
  <strong>AI-powered sysadmin agent for Ubuntu 22.04 VPS, controlled via Telegram.</strong><br>
  <sub>From clean install to production-ready LEMP stack — fully automated.</sub>
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
  <img src="https://img.shields.io/badge/Claude_API-Sonnet_4-6B4FBB?style=flat-square&logo=anthropic&logoColor=white" alt="Claude API">
  <br>
  <!-- Stack -->
  <img src="https://img.shields.io/badge/Nginx-latest-009639?style=flat-square&logo=nginx&logoColor=white" alt="Nginx">
  <img src="https://img.shields.io/badge/MySQL-8.0-4479A1?style=flat-square&logo=mysql&logoColor=white" alt="MySQL 8">
  <img src="https://img.shields.io/badge/PHP-8.3-777BB4?style=flat-square&logo=php&logoColor=white" alt="PHP 8.3">
  <img src="https://img.shields.io/badge/Let's_Encrypt-SSL-003A70?style=flat-square&logo=letsencrypt&logoColor=white" alt="Let's Encrypt">
  <br>
  <!-- Meta -->
  <img src="https://img.shields.io/badge/license-GPL--2.0-22C55E?style=flat-square&logo=gnu&logoColor=white" alt="License GPL-2.0">
  <img src="https://img.shields.io/badge/modules-10-A78BFA?style=flat-square" alt="10 Modules">
  <img src="https://img.shields.io/badge/code-2.8k_lines-F59E0B?style=flat-square" alt="2.8k Lines">
  <img src="https://img.shields.io/badge/PRs-welcome-F472B6?style=flat-square" alt="PRs Welcome">
</p>

---

## Overview

**SyamAdmin** is a self-hosted AI sysadmin agent that runs as a daemon on your Ubuntu VPS. It takes your server from a bare clean install all the way to a production-ready, secured, monitored hosting environment — and keeps it healthy — all controlled through a Telegram bot.

You chat with your server in plain language. It provisions, hardens, monitors, and manages itself.

```
You:  /provision
Bot:  🚀 Installing LEMP stack...
      ✅ Nginx installed
      ✅ MySQL 8 secured (password: xK7#mP...)
      ✅ PHP 8.3 + 15 extensions configured
      ✅ Certbot ready
      🎉 Server siap untuk hosting!

You:  /ai tambah site portal.desa.id dengan laravel
Bot:  ✅ Site portal.desa.id berhasil ditambahkan!
      📁 Root: /var/www/portal.desa.id/public
      🔒 Run /site ssl portal.desa.id to enable HTTPS
```

## ✨ Features

<table>
<tr>
<td width="50%">

### 🚀 Auto Provisioning
One command installs and configures the entire LEMP stack: Nginx (optimized), MySQL 8 (secured), PHP 8.3 (15 extensions), Composer, Certbot, and swap — with real-time progress via Telegram.

### 🔐 Security Hardening
SSH hardening (key-only auth, rate limiting), Fail2Ban with custom jails for SSH + Nginx, UFW firewall with sensible defaults, rootkit scanning, and automatic security updates.

### 📊 Real-Time Monitoring
Continuous background monitoring of CPU, RAM, disk, load average, network, and service health. Threshold-based alerts sent instantly to Telegram with top-process diagnostics.

</td>
<td width="50%">

### 🌐 Site & SSL Management
Add Nginx virtual hosts with one command. Per-site PHP-FPM pools for isolation. One-click SSL via Let's Encrypt with auto-renewal. Supports Laravel and other PHP frameworks out of the box.

### 🧠 AI Brain
Natural language commands via Claude API. Say "restart nginx and check the error log" — the AI parses intent, routes to the right module, and executes. Falls back to keyword parsing if no API key is set.

### 💾 Backup & Audit
Automated database and file backups with compression and retention policies. Every command the agent executes is logged to a SQLite audit trail — full accountability.

</td>
</tr>
</table>

## 🏗 Architecture

```
┌──────────────────┐
│   Telegram Bot   │  ← You chat here
│  (Command + NL)  │
└────────┬─────────┘
         │
┌────────▼─────────┐
│    AI Brain      │  ← Claude API / fallback parser
│  (Intent → Route)│
└────────┬─────────┘
         │
┌────────▼─────────┐
│  Command Router  │  ← Routes to modules
│  + Safety Filter │
└──┬───┬───┬───┬───┘
   │   │   │   │
   ▼   ▼   ▼   ▼
┌────┐┌────┐┌────┐┌──────┐┌────┐┌──────┐
│Prov││Sec ││Fire││Monitor││Site││Backup│
│isi ││uri ││wall││      ││Mgr ││      │
│oner││ty  ││    ││      ││    ││      │
└────┘└────┘└────┘└──────┘└────┘└──────┘
   │   │   │   │      │      │
   ▼   ▼   ▼   ▼      ▼      ▼
┌──────────────────────────────────────┐
│  Ubuntu 22.04 — Managed Services    │
│  Nginx · MySQL 8 · PHP-FPM · UFW   │
│  Fail2Ban · SSH · Certbot           │
└──────────────────────────────────────┘
         │
┌────────▼─────────┐
│  SQLite Database  │
│  Audit · Metrics  │
│  Sites · Alerts   │
└──────────────────┘
```

## 🚀 Quick Start

### Prerequisites

| Requirement | Details |
|-------------|---------|
| **Server** | Ubuntu 22.04 LTS VPS (min 1 GB RAM, 1 vCPU, 20 GB disk) |
| **Access** | Root SSH access |
| **Telegram** | Bot token from [@BotFather](https://t.me/BotFather), your User ID from [@userinfobot](https://t.me/userinfobot) |
| **AI (optional)** | [Anthropic API key](https://console.anthropic.com) for natural language commands |

### Installation

```bash
# 1. Upload to your VPS
scp syamadmin.tar.gz root@YOUR_IP:~/

# 2. SSH in, extract, and install
ssh root@YOUR_IP
tar xzf syamadmin.tar.gz && cd syamadmin
chmod +x install.sh
sudo ./install.sh

# 3. Configure (required before starting)
sudo nano /etc/syamadmin/config.env
```

Set these values in the config file:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_ID=987654321
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx   # optional, enables /ai commands
SERVER_NAME=my-vps-01
```

```bash
# 4. Start the agent
sudo systemctl enable --now syamadmin

# 5. Open Telegram → send /start to your bot 🎉
```

<details>
<summary><strong>What does the installer do?</strong></summary>

1. Verifies Ubuntu 22.04/24.04
2. Installs system dependencies (`python3`, `python3-venv`, `sqlite3`, `htop`, `rkhunter`, etc.)
3. Creates directory structure (`/opt/syamadmin`, `/etc/syamadmin`, `/var/log/syamadmin`, `/var/lib/syamadmin`)
4. Sets up Python venv with all packages (`python-telegram-bot`, `anthropic`, `psutil`, `aiosqlite`, etc.)
5. Registers systemd service with auto-restart
6. Configures logrotate (daily rotation, 14-day retention)
7. Initializes SQLite database (audit_log, metrics, sites, alerts tables)

</details>

## 📱 Telegram Commands

### Core

| Command | Description |
|---------|-------------|
| `/status` | Server dashboard — CPU, RAM, disk, load, network, uptime |
| `/services` | Health check of all managed services |
| `/provision` | Install full LEMP stack (with confirmation) |
| `/logs [service]` | Tail last 30 lines of a log (nginx, mysql, auth, syslog, fail2ban) |
| `/audit` | View recent agent audit trail |

### Site Management

| Command | Description |
|---------|-------------|
| `/site add example.com` | Create vhost + directory + PHP-FPM pool |
| `/site add app.com laravel` | Same, with Laravel-optimized root path |
| `/site ssl example.com` | Enable HTTPS via Let's Encrypt |
| `/site list` | List all managed sites |
| `/site remove example.com` | Remove Nginx config (files preserved) |

### Security & Firewall

| Command | Description |
|---------|-------------|
| `/security` | Run comprehensive security audit |
| `/harden` | Full hardening: SSH + Fail2Ban + UFW + auto-updates |
| `/firewall` | Show UFW status |
| `/fw allow 3306` | Open a port |
| `/fw deny 8080` | Block a port |
| `/fw rules` | List all rules with numbers |

### Backup

| Command | Description |
|---------|-------------|
| `/backup` | Full backup (databases + files) |
| `/backup db` | Backup all MySQL databases |
| `/backup files` | Backup web files + configs |
| `/backup list` | List available backups with sizes |

### AI Commands

| Command | Description |
|---------|-------------|
| `/ai restart nginx` | Natural language → parsed → executed |
| `/ai install redis-server` | AI routes to provisioner module |
| `/ai check why disk is full` | AI runs diagnostics and reports |
| `/ai add site with ssl` | Complex multi-step operations |
| *(any free text)* | Messages without `/` prefix also go to AI |

## 📂 Project Structure

```
syamadmin/
├── install.sh                  # One-click installer
├── config.env.example          # Configuration template
├── syamadmin.py                # Daemon entry point
├── syamadmin.service           # Systemd unit file
├── USER_GUIDE.md               # Comprehensive user guide (ID/EN)
│
├── modules/
│   ├── telegram_bot.py         # Telegram interface (command handlers)
│   ├── brain.py                # AI decision engine (Claude API + fallback)
│   ├── provisioner.py          # LEMP stack installer & optimizer
│   ├── security.py             # SSH hardening, Fail2Ban, audit, rootkit scan
│   ├── firewall.py             # UFW rule management
│   ├── monitor.py              # System metrics, alerts, service health
│   ├── site_manager.py         # Nginx vhost + SSL + PHP-FPM pools
│   ├── backup.py               # Database & file backup engine
│   ├── notifier.py             # Telegram alert & report sender
│   └── executor.py             # Safe shell executor + audit logger
│
├── templates/
│   ├── nginx_vhost.conf        # HTTP vhost template
│   ├── nginx_ssl.conf          # HTTPS vhost template (TLS 1.2/1.3, HSTS)
│   └── php_fpm_pool.conf       # Per-site PHP-FPM pool template
│
├── scripts/
│   ├── harden_ssh.sh           # SSH hardening script
│   ├── setup_fail2ban.sh       # Fail2Ban setup with custom jails
│   └── setup_swap.sh           # Swap file provisioning
│
└── .github/
    └── banner.svg              # Repository header banner
```

## 🔒 Security Model

### Command Safety

Every shell command passes through a safety filter. The following are **permanently blocked** regardless of context:

- `rm -rf /` and filesystem destruction variants
- `mkfs.` (disk format)
- Direct writes to `/dev/sda`
- Fork bombs
- `chmod -R 777 /`
- Piped remote execution (`curl | bash`)

### Audit Trail

Every command executed by the agent is logged to SQLite with timestamp, module, command, duration, user ID, and status. View via `/audit` in Telegram or query directly:

```bash
sqlite3 /var/lib/syamadmin/syamadmin.db \
  "SELECT timestamp, module, action, status FROM audit_log ORDER BY id DESC LIMIT 20;"
```

### Access Control

- Only the configured `TELEGRAM_ADMIN_ID` can control the bot
- Unauthorized access attempts are logged as security events
- Dangerous operations require explicit confirmation with a 2-minute timeout
- Config file permissions are set to `600` (root-only read)

## ⚙️ Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *required* | Bot token from @BotFather |
| `TELEGRAM_ADMIN_ID` | *required* | Your Telegram user ID (numeric) |
| `ANTHROPIC_API_KEY` | *(empty)* | Enables AI natural language commands |
| `SERVER_NAME` | `my-vps-01` | Server identifier shown in notifications |
| `SERVER_TIMEZONE` | `Asia/Makassar` | System timezone |
| `ALERT_THRESHOLD_CPU` | `85` | CPU alert threshold (%) |
| `ALERT_THRESHOLD_RAM` | `90` | RAM alert threshold (%) |
| `ALERT_THRESHOLD_DISK` | `85` | Disk alert threshold (%) |
| `ALERT_THRESHOLD_LOAD` | `4.0` | Load average alert threshold |
| `MONITOR_INTERVAL` | `60` | Monitoring loop interval (seconds) |
| `SSH_PORT` | `22` | SSH port (used by security & firewall modules) |
| `BACKUP_DIR` | `/var/backups/syamadmin` | Backup storage directory |
| `BACKUP_RETENTION_DAYS` | `7` | Days before old backups are auto-deleted |
| `PHP_VERSION` | `8.3` | PHP version to install |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) |

## 🛠 Troubleshooting

<details>
<summary><strong>Agent not responding in Telegram</strong></summary>

```bash
sudo systemctl status syamadmin        # Check if service is running
sudo journalctl -u syamadmin -n 50     # View recent logs
sudo systemctl restart syamadmin       # Restart the agent
```

Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_ID` are correct in `/etc/syamadmin/config.env`.

</details>

<details>
<summary><strong>"Unauthorized" when sending commands</strong></summary>

Only the user matching `TELEGRAM_ADMIN_ID` is authorized. Verify your numeric User ID via [@userinfobot](https://t.me/userinfobot) — it's a number, not your username.

</details>

<details>
<summary><strong>SSL certificate fails</strong></summary>

- Ensure DNS A record points to this server's IP: `dig +short example.com`
- Ensure port 80 is open: `/fw allow 80`
- Let's Encrypt rate limit: max 5 certs per domain per week

</details>

<details>
<summary><strong>Agent keeps restarting (crash loop)</strong></summary>

```bash
sudo systemctl stop syamadmin
# Run manually to see errors directly:
sudo /opt/syamadmin/venv/bin/python3 /opt/syamadmin/syamadmin.py
```

</details>

## 🗺 Roadmap

- [ ] Docker container monitoring integration
- [ ] Webhook support for CI/CD pipelines
- [ ] Web dashboard (localhost) for visual metrics
- [ ] Multi-admin support with role-based permissions
- [ ] Automated performance tuning recommendations
- [ ] Scheduled backup with cron expression support
- [ ] Integration with external monitoring (Uptime Kuma, Grafana)
- [ ] Multi-server management from a single bot

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the GNU General Public License v2.0 — see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — Telegram Bot API wrapper
- [Anthropic Claude API](https://www.anthropic.com) — AI brain powering natural language commands
- [psutil](https://github.com/giampaolo/psutil) — Cross-platform system monitoring
- [Let's Encrypt](https://letsencrypt.org) — Free SSL certificates

---

<p align="center">
  <sub>Built with ☕ for sysadmins who'd rather chat than SSH.</sub><br>
  <sub>Made in Kalimantan 🇮🇩</sub>
</p>
