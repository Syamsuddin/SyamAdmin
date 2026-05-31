# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**SyamAdmin** is an AI-powered sysadmin daemon for Ubuntu 22.04 VPS, controlled entirely through Telegram. It provisions LEMP stacks, manages Nginx sites/SSL, hardens SSH, manages UFW firewall, runs backups, and monitors system health — all via chat commands in Indonesian or English.

The agent runs as a `systemd` service on the VPS itself. Development happens here on macOS; deployment is via `scp` + `install.sh` to a remote Ubuntu server.

## Running the Agent

The agent is **not meant to run locally** — it requires Ubuntu system utilities (`systemctl`, `ufw`, `certbot`, `mysql`, etc.). To run it:

```bash
# On the target Ubuntu VPS after install:
sudo systemctl start syamadmin
sudo systemctl status syamadmin
sudo journalctl -u syamadmin -f          # tail live logs

# Debug mode (run directly, see all output):
sudo /opt/syamadmin/venv/bin/python3 /opt/syamadmin/syamadmin.py

# Query the audit database directly:
sqlite3 /var/lib/syamadmin/syamadmin.db \
  "SELECT timestamp, module, action, status FROM audit_log ORDER BY id DESC LIMIT 20;"
```

## Deploying Changes

```bash
# Re-package and upload to VPS:
tar czf syamadmin.tar.gz --exclude='.git' --exclude='*.tar.gz' .
scp syamadmin.tar.gz root@YOUR_IP:~/

# On VPS: extract and overwrite, then restart:
tar xzf syamadmin.tar.gz -C /opt/syamadmin --strip-components=1
sudo systemctl restart syamadmin
```

## Architecture

The agent has two concurrent async tasks running in `syamadmin.py`:
1. **`SyamAdminBot`** — Telegram polling loop (command router)
2. **`SystemMonitor`** — Background metrics collection + threshold alerts

All user interactions flow:
```
Telegram message → SyamAdminBot (command/text handler)
                 → AIBrain.process_command()  [if /ai or free text]
                 → specific module method
                 → CommandExecutor.run()       [shell execution]
                 → SQLite audit_log            [every command logged]
                 → Notifier.send()             [Telegram reply]
```

## Module Responsibilities

| Module | File | Purpose |
|--------|------|---------|
| `SyamAdminBot` | `modules/telegram_bot.py` | Command handlers, confirmation flow, free-text AI routing |
| `AIBrain` | `modules/brain.py` | Claude API call → structured JSON action; keyword fallback when no API key |
| `CommandExecutor` | `modules/executor.py` | Async shell execution, safety filter (BLOCKED_PATTERNS), SQLite audit log |
| `SystemMonitor` | `modules/monitor.py` | Metrics loop, threshold alerts, service health checks |
| `Notifier` | `modules/notifier.py` | Telegram message sender (used by modules to push alerts) |
| `Provisioner` | `modules/provisioner.py` | LEMP stack installer |
| `SecurityManager` | `modules/security.py` | SSH hardening, Fail2Ban, rootkit scan, auto-updates |
| `FirewallManager` | `modules/firewall.py` | UFW rule management |
| `SiteManager` | `modules/site_manager.py` | Nginx vhosts, PHP-FPM pools, Let's Encrypt SSL |
| `BackupManager` | `modules/backup.py` | MySQL dump, file tar, retention cleanup |

## Key Design Patterns

**Confirmation flow**: Dangerous operations set a pending confirmation in `_pending_confirmations[admin_id]` with a 120-second expiry. Two-tier confirmation:
- **Non-destructive actions** (`ai`, `add_cron`, `optimize_system`): accept affirmative words (`ya/iya/ok/oke/yes/y/lanjut/setuju/gas`) OR the numeric OTP code.
- **Destructive actions** (`provision`, `remove_site`, `deny_ssh`, `change_ssh_port`, `restore`, `repair_service`, `wizard_provision`): strictly require the OTP code. Affirmative words are rejected with a reminder to use OTP.

**Safety filter**: `CommandExecutor._is_blocked()` checks every shell command against `BLOCKED_PATTERNS` before execution. This cannot be bypassed — it runs before every `executor.run()` call.

**AI Brain JSON contract**: `AIBrain.process_command()` returns a dict with keys `intent`, `module`, `action`, `params`, `confirmation_needed`, `message`. The `_execute_ai_action()` method in the bot dynamically routes via `getattr(module, action)(**params)`.

**Module wiring**: All modules are instantiated in `syamadmin.py:main()` and passed into the bot as a `modules` dict. Modules receive `executor` and `notifier` at construction time.

**Bilingual support**: Bot messages and the AI system prompt are in Indonesian (`id`). The Claude model used is `claude-sonnet-4-20250514`.

## Configuration

Config lives at `/etc/syamadmin/config.env` on the VPS (permissions `600`). Template: `config.env.example`. Required vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_ID`. All others have defaults.

The daemon reads config via `python-dotenv` at startup. A `CONFIG_PATH` env override allows pointing to a different file (useful for testing).

## SQLite Schema

The database at `/var/lib/syamadmin/syamadmin.db` has these tables (created by `CommandExecutor._ensure_db()` and `SiteManager`):
- `audit_log` — every shell command with timestamp, module, action, status
- `metrics` — historical resource snapshots
- `sites` — managed Nginx virtual hosts
- `alerts` — sent alert history

## Nginx / PHP Templates

`templates/nginx_vhost.conf` and `templates/nginx_ssl.conf` are Jinja-style templates with `{domain}`, `{webroot}`, `{php_version}` placeholders. `SiteManager` reads and renders these via `.format()` or string replacement — check the actual implementation before editing placeholders.