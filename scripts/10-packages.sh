#!/bin/bash
# 10-packages.sh — runs INSIDE the i386 chroot
# Target package set for the Eee PC 701 image (Debian 12 bookworm, i386)
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

cat > /etc/apt/sources.list <<'EOF'
deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware
deb http://deb.debian.org/debian bookworm-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware
deb http://deb.debian.org/debian bookworm-backports main contrib non-free non-free-firmware
EOF

cat > /etc/apt/apt.conf.d/99eeepc <<'EOF'
APT::Install-Recommends "true";
APT::Install-Suggests "false";
Acquire::Retries "5";
EOF

# Keep the image small: skip /usr/share/doc (keep copyright files)
cat > /etc/dpkg/dpkg.cfg.d/01_nodoc <<'EOF'
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/lintian/*
path-exclude=/usr/share/linda/*
EOF

# Preseed keyboard + timezone so nothing is interactive
debconf-set-selections <<'EOF'
keyboard-configuration keyboard-configuration/layout select us
keyboard-configuration keyboard-configuration/variant select English (US)
tzdata tzdata/Areas select Etc
tzdata tzdata/Zones/Etc select UTC
locales locales/default-environment-locale select en_US.UTF-8
locales locales/locales_to_be_generated multiselect en_US.UTF-8 UTF-8
EOF

apt-get update
apt-get install -y --no-install-recommends locales tzdata keyboard-configuration console-setup

apt-get install -y \
  systemd-sysv dbus sudo kmod cpio initramfs-tools grub-pc \
  network-manager network-manager-gnome wpasupplicant iw wireless-tools rfkill \
  openssh-server avahi-daemon \
  curl wget rsync tmux htop ncdu less file nano pciutils usbutils \
  alsa-utils volumeicon-alsa \
  earlyoom tlp \
  cloud-guest-utils e2fsprogs dosfstools ntfs-3g exfatprogs \
  xserver-xorg-core xserver-xorg xserver-xorg-video-intel \
  xserver-xorg-video-fbdev xserver-xorg-video-vesa xserver-xorg-input-libinput \
  x11-xserver-utils x11-utils xdg-user-dirs xdg-utils \
  openbox tint2 pcmanfm lxterminal mousepad lightdm lightdm-gtk-greeter \
  lxqt-policykit \
  firefox-esr netsurf-gtk feh \
  fonts-dejavu-core fonts-liberation \
  acpi acpid intel-microcode \
  systemd-timesyncd

echo "=== packages done ==="
apt-get clean
