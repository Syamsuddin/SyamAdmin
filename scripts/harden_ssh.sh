#!/usr/bin/env bash
# SyamAdmin — SSH Hardening Script
set -euo pipefail

SSH_PORT="${SSH_PORT:-22}"

echo "[*] Backing up sshd_config..."
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%s)

echo "[*] Applying SSH hardening..."
cat > /etc/ssh/sshd_config.d/99-syamadmin-hardening.conf << EOF
# SyamAdmin SSH Hardening - $(date)
Port ${SSH_PORT}
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PermitEmptyPasswords no
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
MaxAuthTries 3
MaxSessions 3
ClientAliveInterval 300
ClientAliveCountMax 2
LoginGraceTime 30
AllowAgentForwarding no
AllowTcpForwarding no
PrintMotd no
EOF

echo "[*] Testing SSH config..."
sshd -t

echo "[*] Reloading SSH..."
systemctl reload sshd

echo "[+] SSH hardening applied successfully."
echo "    Port: ${SSH_PORT}"
echo "    Root login: key-only"
echo "    Password auth: disabled"
