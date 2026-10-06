#!/bin/bash
# 61-fixes.sh — inside chroot: correct ssh host-key ordering and zram setup
set -euo pipefail

# --- ssh: generate host keys BEFORE the stock config test ---
cat > /etc/systemd/system/ssh.service.d/override.conf <<'EOF'
[Service]
ExecStartPre=
ExecStartPre=/usr/bin/ssh-keygen -A
ExecStartPre=/usr/sbin/sshd -t
EOF

# --- zram: sysfs-driven, no zramctl dependency ---
cat > /etc/systemd/system/zram-swap.service <<'EOF'
[Unit]
Description=Configure zram swap
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/bin/sh -c "[ -e /dev/zram0 ] || cat /sys/class/zram-control/hot_add >/dev/null; echo lz4 > /sys/block/zram0/comp_algorithm 2>/dev/null || true; echo 1073741824 > /sys/block/zram0/disksize; mkswap /dev/zram0 >/dev/null; swapon -p 100 /dev/zram0"
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF

echo FIXES_APPLIED
