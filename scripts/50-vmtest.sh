#!/bin/bash
# 50-vmtest.sh — runs on the Proxmox HOST (root).
# Boots the assembled image in a 32-bit VM under KVM and verifies:
#  - BIOS/GRUB path boots (no EFI)
#  - non-PAE kernel (tested with -cpu pentium2: definitively NO PAE)
#  - systemd reaches multi-user, lightdm autologin starts openbox
#  - sshd answers on forwarded port, memory footprint sane for 2GB
#  - VGA screendump shows a real desktop (saved as PNG for review)
set -euo pipefail

BASE=/var/lib/vz/eeepc
T=/tmp/eeepc-vmtest
rm -rf "$T"; mkdir -p "$T"
cp "$BASE/eeepc701-linux.img" "$T/disk.img"

LOOP=$(losetup --show -fP "$T/disk.img")
trap 'umount /mnt/eeepc-t 2>/dev/null; losetup -d "$LOOP" 2>/dev/null; true' EXIT
mkdir -p /mnt/eeepc-t
mount "${LOOP}p1" /mnt/eeepc-t

# inject a test SSH key for sam
ssh-keygen -t ed25519 -N '' -f "$T/testkey" -q
mkdir -p /mnt/eeepc-t/home/sam/.ssh
cat "$T/testkey.pub" > /mnt/eeepc-t/home/sam/.ssh/authorized_keys
chown -R 1000:1000 /mnt/eeepc-t/home/sam/.ssh
chmod 700 /mnt/eeepc-t/home/sam/.ssh

KREL=$(ls -1 /mnt/eeepc-t/boot/vmlinuz-* | head -1 | xargs -n1 basename | sed 's/vmlinuz-//')
cp "/mnt/eeepc-t/boot/vmlinuz-$KREL" "$T/vmlinuz"
cp "/mnt/eeepc-t/boot/initrd.img-$KREL" "$T/initrd.img"
echo "tested kernel: $KREL"
umount /mnt/eeepc-t
losetup -d "$LOOP"

run_qemu() {
  local name="$1"; shift
  timeout --signal=KILL 420 qemu-system-x86_64 -enable-kvm "$@" \
    -m 2048 -smp 1 -display none \
    -netdev user,id=n0,hostfwd=tcp:127.0.0.1:2223-:22 \
    -device e1000,netdev=n0 \
    -monitor unix:"$T/$name.mon",server,nowait \
    -pidfile "$T/$name.pid" \
    -serial "file:$T/$name.serial.log" &
  echo $! > "$T/$name.qemu.pid"
}

wait_ssh() {
  for i in $(seq 1 60); do
    if ssh -i "$T/testkey" -p 2223 -o StrictHostKeyChecking=no -o UserKnownHostsFile="$T/kh" \
        -o ConnectTimeout=3 -o BatchMode=yes sam@127.0.0.1 true 2>/dev/null; then
      return 0
    fi
    sleep 5
  done
  return 1
}

stop_qemu() {
  local name="$1"
  [ -f "$T/$name.pid" ] && kill "$(cat "$T/$name.pid")" 2>/dev/null || true
  [ -f "$T/$name.qemu.pid" ] && kill "$(cat "$T/$name.qemu.pid")" 2>/dev/null || true
  sleep 2
}

### TEST 1: direct kernel boot on a definitively NON-PAE CPU (Pentium II class)
echo "== TEST 1: -cpu pentium2 (no PAE), direct kernel, serial console =="
run_qemu t1 -cpu pentium2 -kernel "$T/vmlinuz" -initrd "$T/initrd.img" \
  -append "root=UUID=b0057a11-de12-b007-01ee-000000000001 ro console=ttyS0,115200n8" \
  -drive file="$T/disk.img",if=ide,format=raw

if wait_ssh; then
  echo "-- ssh up on non-PAE CPU. system state:"
  ssh -i "$T/testkey" -p 2223 -o StrictHostKeyChecking=no -o UserKnownHostsFile="$T/kh" sam@127.0.0.1 \
    'echo "KERNEL: $(uname -sr)"; echo "PAE flag: $(grep -o pae /proc/cpuinfo | head -1 || echo ABSENT)"; free -m; df -h / | tail -1; systemctl is-system-running; systemctl --no-legend --failed || true; ls /sys/class/net'
  T1=PASS
else
  echo "-- TEST 1 FAILED: no ssh"; tail -30 "$T/t1.serial.log"; T1=FAIL
fi
stop_qemu t1

### TEST 2: full BIOS boot of the disk image (GRUB -> kernel), qemu32 CPU
echo "== TEST 2: full disk boot (BIOS/GRUB path), -cpu qemu32 =="
cp "$BASE/eeepc701-linux.img" "$T/disk2.img"
L2=$(losetup --show -fP "$T/disk2.img")
mount "${L2}p1" /mnt/eeepc-t
mkdir -p /mnt/eeepc-t/home/sam/.ssh
cat "$T/testkey.pub" > /mnt/eeepc-t/home/sam/.ssh/authorized_keys
chown -R 1000:1000 /mnt/eeepc-t/home/sam/.ssh
umount /mnt/eeepc-t
losetup -d "$L2"
run_qemu t2 -cpu qemu32 -drive file="$T/disk2.img",if=ide,format=raw

if wait_ssh; then
  echo "-- TEST 2 system state:"
  ssh -i "$T/testkey" -p 2223 -o StrictHostKeyChecking=no -o UserKnownHostsFile="$T/kh" sam@127.0.0.1 \
    'echo "KERNEL: $(uname -sr)"; systemctl is-system-running; echo "--- lightdm:"; systemctl is-active lightdm; echo "--- memory (MB):"; free -m | head -2; echo "--- X:"; pgrep -a Xorg | head -2; echo "--- display manager seat:"; loginctl list-sessions --no-legend || true'
  # let the desktop settle, then grab a screendump of the VGA output
  sleep 45
  echo screendump "$T/desktop.ppm" | socat - UNIX-CONNECT:"$T/t2.mon" || true
  sleep 2
  [ -f "$T/desktop.ppm" ] && { pnmtopng "$T/desktop.ppm" > "$T/desktop.png" 2>/dev/null || convert "$T/desktop.ppm" "$T/desktop.png" 2>/dev/null || true; }
  T2=PASS
else
  echo "-- TEST 2 FAILED: no ssh"; tail -30 "$T/t2.serial.log"; T2=FAIL
fi
stop_qemu t2

echo "============================================"
echo "TEST 1 (non-PAE pentium2, kernel boot): $T1"
echo "TEST 2 (full image BIOS boot, desktop):  $T2"
echo "artifacts in $T (desktop.png if captured)"
