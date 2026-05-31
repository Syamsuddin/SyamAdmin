#!/usr/bin/env bash
# SyamAdmin — Fail2Ban Setup
set -euo pipefail

SSH_PORT="${SSH_PORT:-22}"

echo "[*] Installing fail2ban..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fail2ban

echo "[*] Configuring jail rules..."
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
backend = systemd
action = %(action_mwl)s

[sshd]
enabled = true
port = ${SSH_PORT}
maxretry = 3
bantime = 7200

[nginx-http-auth]
enabled = true
port = http,https

[nginx-botsearch]
enabled = true
port = http,https

[nginx-limit-req]
enabled = true
port = http,https

[nginx-bad-request]
enabled = true
port = http,https
filter = nginx-bad-request
logpath = /var/log/nginx/access.log
maxretry = 5
EOF

# Create custom nginx-bad-request filter
cat > /etc/fail2ban/filter.d/nginx-bad-request.conf << 'EOF'
[Definition]
failregex = ^<HOST> .* "(GET|POST|HEAD).*HTTP.*" 400
ignoreregex =
EOF

echo "[*] Enabling and starting fail2ban..."
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "[+] Fail2ban configured successfully."
fail2ban-client status
