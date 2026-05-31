#!/usr/bin/env bash
# ============================================
# SyamAdmin — Git Init & Push to GitHub
# Jalankan di direktori syamadmin/ hasil extract
# ============================================
set -euo pipefail

REPO_URL="https://github.com/Syamsuddin/SyamAdmin.git"
BRANCH="main"

echo "🚀 Initializing SyamAdmin repository..."
echo ""

# Init repo
git init -b "$BRANCH"

# Add all files
git add -A

# Show what will be committed
echo "📋 Files to commit:"
git status --short
echo ""

# Commit
git commit -m "🚀 Initial commit: SyamAdmin v1.0

AI-powered sysadmin agent for Ubuntu 22.04 VPS.

Features:
- LEMP stack auto-provisioning (Nginx, MySQL 8, PHP 8.3)
- Security hardening (SSH, Fail2Ban, UFW)
- Real-time monitoring with Telegram alerts
- Site & SSL management (Let's Encrypt)
- AI natural language commands (Claude API)
- Automated backup with retention
- Full audit trail

Controlled entirely via Telegram bot."

# Add remote
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"

# Push
echo ""
echo "📤 Pushing to $REPO_URL ..."
git push -u origin "$BRANCH"

echo ""
echo "✅ Done! Repository live at: https://github.com/Syamsuddin/SyamAdmin"
