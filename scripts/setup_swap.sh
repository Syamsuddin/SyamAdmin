#!/usr/bin/env bash
# SyamAdmin — Swap Setup
set -euo pipefail

SWAP_SIZE="${SWAP_SIZE:-2G}"

if swapon --show | grep -q '/swapfile'; then
    echo "[*] Swap already exists:"
    swapon --show
    exit 0
fi

echo "[*] Creating ${SWAP_SIZE} swap file..."
fallocate -l "${SWAP_SIZE}" /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

echo "[*] Making swap permanent..."
if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "[*] Optimizing swappiness..."
sysctl vm.swappiness=10
if ! grep -q 'vm.swappiness' /etc/sysctl.conf; then
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

echo "[+] Swap configured:"
swapon --show
free -h
