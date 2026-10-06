#!/usr/bin/env python3
# 73-console-pty.py — boot image with a python-allocated PTY as serial console.
import subprocess, time, sys, os, re, fcntl, select, pty

BASE = "/var/lib/vz/eeepc"
VT = "/var/lib/vz/eeepc/vt"
T = "/tmp/eeepc-pty"
SERLOG = f"{T}/session.log"

os.makedirs(T, exist_ok=True)
os.makedirs(VT, exist_ok=True)
os.makedirs("/mnt/dbg", exist_ok=True)
subprocess.run(["rm", "-f", f"{T}/disk.img"], check=True)
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

# allocate our own PTY; qemu opens the slave as the serial port
mfd, sfd = pty.openpty()
slave = os.ttyname(sfd)

proc = subprocess.Popen([
    "qemu-system-x86_64", "-enable-kvm", "-cpu", "qemu32", "-m", "2048", "-smp", "1",
    "-kernel", f"{VT}/{k}", "-initrd", f"{VT}/{i}",
    "-append", "root=UUID=b0057a11-de12-b007-01ee-000000000001 ro console=ttyS0,115200n8",
    "-drive", f"file={T}/disk.img,if=ide,format=raw",
    "-netdev", "user,id=n0,hostfwd=tcp:127.0.0.1:2228-:22",
    "-device", "e1000,netdev=n0",
    "-display", "none",
    "-serial", slave,
    "-monitor", "none",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
os.close(sfd)
print("serial slave:", slave, flush=True)

sess = open(SERLOG, "wb", buffering=0)
buf = b""
def expect(pattern, timeout=300):
    global buf
    end = time.time() + timeout
    while time.time() < end:
        ready, _, _ = select.select([mfd], [], [], 1)
        if ready:
            try:
                data = os.read(mfd, 4096)
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
    os.write(mfd, line.encode() + b"\r")

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
