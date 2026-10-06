#!/usr/bin/env python3
# 72-console-pty.py — boot image, serial on a host PTY, drive console via the PTY.
import subprocess, time, sys, os, re, fcntl

BASE = "/var/lib/vz/eeepc"
VT = "/var/lib/vz/eeepc/vt"
T = "/tmp/eeepc-pty"
SERLOG = f"{T}/session.log"

os.makedirs(T, exist_ok=True)
os.makedirs(VT, exist_ok=True)
os.makedirs("/mnt/dbg", exist_ok=True)
subprocess.run(["rm", "-f", f"{T}/disk.img", f"{T}/qemu.err"], check=True)
subprocess.run(["cp", f"{BASE}/eeepc701-linux.img", f"{T}/disk.img"], check=True)

loop = subprocess.check_output(["losetup", "--show", "-fP", f"{T}/disk.img"], text=True).strip()
subprocess.run(["mount", loop + "p1", "/mnt/dbg"], check=True)
for f in os.listdir("/mnt/dbg/boot"):
    if f.startswith(("vmlinuz-", "initrd.img-")) and not os.path.exists(f"{VT}/{f}"):
        subprocess.run(["cp", f"/mnt/dbg/boot/{f}", f"{VT}/{f}"], check=True)
k = [f for f in os.listdir("/mnt/dbg/boot") if f.startswith("vmlinuz-")][0]
i = [f for f in os.listdir("/mnt/dbg/boot") if f.startswith("initrd.img-")][0]
subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", f"{T}/testkey", "-q"], check=True)
os.makedirs("/mnt/dbg/home/sam/.ssh", exist_ok=True)
open("/mnt/dbg/home/sam/.ssh/authorized_keys", "w").write(open(f"{T}/testkey.pub").read())
subprocess.run(["chown", "-R", "1000:1000", "/mnt/dbg/home/sam/.ssh"], check=True)
subprocess.run(["umount", "/mnt/dbg"], check=True)
subprocess.run(["losetup", "-d", loop], check=True)

proc = subprocess.Popen([
    "qemu-system-x86_64", "-enable-kvm", "-cpu", "qemu32", "-m", "2048", "-smp", "1",
    "-kernel", f"{VT}/{k}", "-initrd", f"{VT}/{i}",
    "-append", "root=UUID=b0057a11-de12-b007-01ee-000000000001 ro console=ttyS0,115200n8",
    "-drive", f"file={T}/disk.img,if=ide,format=raw",
    "-netdev", "user,id=n0,hostfwd=tcp:127.0.0.1:2227-:22",
    "-device", "e1000,netdev=n0",
    "-display", "none",
    "-serial", "pty",
    "-monitor", "none",
], stderr=subprocess.PIPE, text=True, bufsize=1)

import select
pts = None
ready, _, _ = select.select([proc.stderr], [], [], 30)
if ready:
    line = proc.stderr.readline()
    m = re.search(r"/dev/pts/\d+", line)
    if m:
        pts = m.group(0)
if not pts:
    print("NO PTY, stderr line was:", repr(line) if 'line' in dir() else 'none'); proc.kill(); sys.exit(1)
print("serial pts:", pts, flush=True)

fd = os.open(pts, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK)
sess = open(SERLOG, "wb", buffering=0)

buf = b""
def expect(pattern, timeout=300):
    global buf
    end = time.time() + timeout
    while time.time() < end:
        ready, _, _ = select.select([fd], [], [], 1)
        if ready:
            try:
                data = os.read(fd, 4096)
            except OSError:
                data = b""
            if data:
                buf += data
                sess.write(data)
                os.write(1, data)
        if re.search(pattern, buf.decode(errors="replace")):
            return True
    return False

def send(line):
    os.write(fd, line.encode() + b"\r")

print("=== waiting for login prompt ===", flush=True)
if not expect(r"login:"):
    print("!!! no login prompt"); proc.kill(); sys.exit(1)
send("sam"); time.sleep(2); send("eeepc"); time.sleep(4)
for c in [
    "systemctl --no-pager status ssh.service 2>&1 | tail -15",
    "journalctl -b -u ssh.service --no-pager 2>&1 | tail -20",
    "ls -la /etc/ssh/ /run/sshd 2>&1",
    "/usr/sbin/sshd -t; echo SSDT=$?",
    "systemctl --no-pager status zram-swap.service 2>&1 | tail -10",
    "free -m; swapon --show; echo DEBUG_DONE",
]:
    send(c); time.sleep(6)
expect(r"DEBUG_DONE", 120)
proc.terminate()
print("\n=== end ===")
