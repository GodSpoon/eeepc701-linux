#!/bin/bash
# 90-cleanup.sh — runs INSIDE the chroot, AFTER kernel build + configure.
# Removes build toolchain, sanitizes the system for image cloning.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get purge -y build-essential g++ gcc-12 gcc cpp cpp-12 make m4 \
  dpkg-dev binutils binutils-i686-linux-gnu libstdc++-12-dev libc6-dev \
  linux-libc-dev libelf-dev libssl-dev flex bison bc libfl-dev libfl2 \
  libncurses-dev libncurses6 2>/dev/null || true
apt-get autoremove --purge -y
apt-get clean

# Sanitize for cloning: unique IDs and host keys are created on first boot
rm -f /etc/machine-id /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_*
rm -f /var/lib/eeepc-expanded
journalctl --vacuum-size=1M >/dev/null 2>&1 || true
rm -rf /var/log/*.gz /var/log/apt/*.gz /tmp/* /var/tmp/*
find /var/log -type f -exec truncate -s0 {} \; 2>/dev/null || true

echo "=== cleanup done ==="
df -h / | tail -1
du -sh / 2>/dev/null | tail -1
