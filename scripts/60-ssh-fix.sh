#!/bin/bash
# 60-ssh-fix.sh — inside chroot: ssh host keys generated before sshd starts
set -euo pipefail
mkdir -p /etc/systemd/system/ssh.service.d
printf '[Service]\nExecStartPre=/usr/bin/ssh-keygen -A\n' > /etc/systemd/system/ssh.service.d/override.conf
rm -f /etc/systemd/system/firstboot-ssh-keys.service
rm -f /etc/systemd/system/multi-user.target.wants/firstboot-ssh-keys.service
ls -la /etc/systemd/system/ssh.service.d/
