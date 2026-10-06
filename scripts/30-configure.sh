#!/bin/bash
# 30-configure.sh — runs INSIDE the chroot. Configures hostname, user, fstab,
# desktop autologin, zram, first-boot grow, ssh, ssh host key regen, etc.
set -euo pipefail

IMG_UUID="b0057a11-de12-b007-01ee-000000000001"

# --- hostname / hosts ---
echo "eeepc701" > /etc/hostname
cat > /etc/hosts <<EOF
127.0.0.1	localhost
127.0.1.1	eeepc701
::1		localhost ip6-localhost ip6-loopback
EOF

# --- timezone + locale ---
ln -sf /usr/share/zoneinfo/Etc/UTC /etc/localtime
echo "Etc/UTC" > /etc/timezone
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8

# --- fstab (root is written with the UUID we will mkfs with) ---
cat > /etc/fstab <<EOF
UUID=$IMG_UUID	/	ext4	defaults,noatime,commit=60	0	1
tmpfs		/tmp	tmpfs	defaults,nosuid,nodev	0	0
EOF

# --- user: sam / eeepc (sudo) ---
useradd -m -s /bin/bash sam
echo 'sam:eeepc' | chpasswd
usermod -aG sudo sam
# root login locked (sudo only)
passwd -l root

# --- sshd: no root login; host keys are generated before each start (clone-safe) ---
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
mkdir -p /etc/systemd/system/ssh.service.d
cat > /etc/systemd/system/ssh.service.d/override.conf <<'EOF'
[Service]
ExecStartPre=
ExecStartPre=/usr/bin/ssh-keygen -A
ExecStartPre=/usr/sbin/sshd -t
EOF
systemctl enable ssh.service

# --- zram swap (1G lz4) ---
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
systemctl enable zram-swap.service
cat > /etc/sysctl.d/50-eeepc.conf <<'EOF'
vm.swappiness=150
EOF

# --- NetworkManager: disable wifi powersave (ath5k stability), enable services ---
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/10-eeepc.conf <<'EOF'
[device]
wifi.powersave = 2
EOF
systemctl enable NetworkManager avahi-daemon acpid tlp earlyoom systemd-timesyncd

# --- journald cap ---
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/50-eeepc.conf <<'EOF'
[Journal]
SystemMaxUse=30M
EOF

# --- Eee PC platform module (hotkeys, fan) ---
echo "eeepc-laptop" > /etc/modules-load.d/eeepc.conf

# --- audio: unmute on boot ---
cat > /etc/systemd/system/alsa-unmute.service <<'EOF'
[Unit]
Description=Unmute ALSA Master/PCM
After=sound.target
[Service]
Type=oneshot
ExecStart=/bin/sh -c "amixer -q sset Master on unmute || true; amixer -q sset PCM on unmute || true; amixer -q sset Master 75% || true"
[Install]
WantedBy=multi-user.target
EOF
systemctl enable alsa-unmute.service

# --- first-boot: grow root partition/filesystem to fill the SD card ---
cat > /usr/local/sbin/expand-root.sh <<'EOF'
#!/bin/bash
set -e
[ -f /var/lib/eeepc-expanded ] && exit 0
src=$(findmnt -n -o SOURCE /)
disk=""
partnum=""
case "$src" in
  /dev/sd[a-z][0-9]*)   disk="${src:0:-1}"; partnum="${src: -1}" ;;
  /dev/mmcblk[0-9]p[0-9]*) disk="${src%p*}"; partnum="${src##*p}" ;;
  *) exit 0 ;;
esac
growpart "$disk" "$partnum" || exit 0
resize2fs "$src" || exit 0
touch /var/lib/eeepc-expanded
EOF
chmod +x /usr/local/sbin/expand-root.sh
cat > /etc/systemd/system/expand-root.service <<'EOF'
[Unit]
Description=Grow root partition to fill SD card (first boot)
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/expand-root.sh
[Install]
WantedBy=multi-user.target
EOF
systemctl enable expand-root.service

# --- lightdm autologin into openbox ---
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-autologin.conf <<'EOF'
[Seat:*]
autologin-user=sam
autologin-user-timeout=0
user-session=openbox
EOF

# --- openbox session for sam: panel, applets, keybinds ---
mkdir -p /home/sam/.config/openbox
cat > /home/sam/.config/openbox/autostart <<'EOF'
tint2 &
nm-applet &
volumeicon &
EOF
cat > /home/sam/.config/openbox/menu.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/menu">
  <menu id="root-menu" label="Openbox 3">
    <item label="Terminal"><action name="Execute"><execute>lxterminal</execute></action></item>
    <item label="Web browser (Firefox)"><action name="Execute"><execute>firefox-esr</execute></action></item>
    <item label="Light browser (Netsurf)"><action name="Execute"><execute>netsurf</execute></action></item>
    <item label="Files"><action name="Execute"><execute>pcmanfm</execute></action></item>
    <item label="Text editor"><action name="Execute"><execute>mousepad</execute></action></item>
    <separator/>
    <item label="Network connections"><action name="Execute"><execute>nm-connection-editor</execute></action></item>
    <item label="Volume control"><action name="Execute"><execute>lxterminal -e alsamixer</execute></action></item>
    <separator/>
    <item label="Lock screen"><action name="Execute"><execute>lxlock</execute></action></item>
    <item label="Reboot"><action name="Execute"><execute>systemctl reboot</execute></action></item>
    <item label="Shutdown"><action name="Execute"><execute>systemctl poweroff</execute></action></item>
  </menu>
</openbox_config>
EOF
cat > /home/sam/.config/openbox/rc.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <applications>
    <application class="*">
      <maximized>false</maximized>
    </application>
  </applications>
  <keyboard>
    <keybind key="W-Return"><action name="Execute"><execute>lxterminal</execute></action></keybind>
    <keybind key="W-F"><action name="Execute"><execute>firefox-esr</execute></action></keybind>
    <keybind key="W-D"><action name="ShowMenu"><menu>root-menu</menu></action></keybind>
    <keybind key="XF86AudioRaiseVolume"><action name="Execute"><execute>amixer -q sset Master 5%+</execute></action></keybind>
    <keybind key="XF86AudioLowerVolume"><action name="Execute"><execute>amixer -q sset Master 5%-</execute></action></keybind>
    <keybind key="XF86AudioMute"><action name="Execute"><execute>amixer -q sset Master toggle</execute></action></keybind>
  </keyboard>
  <mouse><context name="Client"><mousebind button="A-Left" action="Press"><action name="Focus"/><action name="Raise"/><action name="Unshade"/></mousebind></context></mouse>
</openbox_config>
EOF
# Dark GTK theme by default
mkdir -p /home/sam/.config/gtk-3.0 /home/sam/.config/gtk-2.0
cat > /home/sam/.config/gtk-3.0/settings.ini <<'EOF'
[Settings]
gtk-theme-name=Adwaita-dark
gtk-icon-theme-name=Adwaita
gtk-font-name=DejaVu Sans 10
EOF
echo 'gtk-theme-name="Adwaita-dark"' > /home/sam/.config/gtk-2.0/gtkrc
# terminal sane defaults
mkdir -p /home/sam/.config/lxterminal
cat > /home/sam/.config/lxterminal/lxterminal.conf <<'EOF'
[general]
fontname=DejaVu Sans Mono 10
bgcolor=#000000000000
fgcolor=#fffff8f8eeee
EOF
chown -R sam:sam /home/sam/.config

# --- MOTD with quick reference ---
cat > /etc/motd <<'EOF'

  EeePC 701 Linux — Debian 12 (bookworm) i386, kernel 6.12 LTS (non-PAE)
  ------------------------------------------------------------------------
  user: sam   password: eeepc   (change with: passwd)
  sudo works for sam. Root login is locked.

  Desktop: Openbox. Right-click desktop for menu. Panel: tint2.
  Wifi: click the nm-applet icon in the panel.
  This system runs from SD; swap is zram (RAM-backed, no SD wear).

EOF

echo "=== configure done ==="
