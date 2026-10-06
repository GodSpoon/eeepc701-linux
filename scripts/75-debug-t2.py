#!/usr/bin/env python3
# 75-debug-t2.py — full GRUB disk boot; select serial-console entry; diagnose sshd.
import subprocess, time, os, re, select, socket, pty, sys

BASE = "/var/lib/vz/eeepc"
T = "/tmp/eeepc-t2dbg"
os.makedirs(T, exist_ok=True)
os.makedirs("/mnt/dbg", exist_ok=True)
subprocess.run(["rm", "-f", f"{T}/disk.img", f"{T}/t.mon"], check=True)
subprocess.run(["cp", f"{BASE}/eeepc701-linux.img", f"{T}/disk.img"], check=True)

# inject ssh test key
loop = subprocess.check_output(["losetup", "--show", "-fP", f"{T}/disk.img"], text=True).strip()
subprocess.run(["mount", loop + "p1", "/mnt/dbg"], check=True)
subprocess.run(["rm", "-f", f"{T}/testkey", f"{T}/testkey.pub"], check=True)
subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", f"{T}/testkey", "-q"], check=True)
os.makedirs("/mnt/dbg/home/sam/.ssh", exist_ok=True)
open("/mnt/dbg/home/sam/.ssh/authorized_keys", "w").write(open(f"{T}/testkey.pub").read())
subprocess.run(["chown", "-R", "1000:1000", "/mnt/dbg/home/sam/.ssh"], check=True)
subprocess.run(["umount", "/mnt/dbg"], check=True)
subprocess.run(["losetup", "-d", loop], check=True)

mfd, sfd = pty.openpty()
slave = os.ttyname(sfd)
proc = subprocess.Popen([
    "qemu-system-x86_64", "-enable-kvm", "-cpu", "qemu32", "-m", "2048", "-smp", "1",
    "-drive", f"file={T}/disk.img,if=ide,format=raw",
    "-netdev", "user,id=n0,hostfwd=tcp:127.0.0.1:2229-:22",
    "-device", "e1000,netdev=n0",
    "-display", "none", "-vga", "std",
    "-serial", slave,
    "-monitor", f"unix:{T}/t.mon,server=on,wait=off",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
os.close(sfd)
print("serial slave:", slave, flush=True)

def mon(cmd):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(5)
    s.connect(f"{T}/t.mon"); time.sleep(0.2)
    s.recv(8192); s.sendall((cmd + "\n").encode()); time.sleep(0.4)
    try: out = s.recv(65536).decode(errors="replace")
    except socket.timeout: out = ""
    s.close(); return out

# GRUB menu: default timeout 5s. Select 3rd entry (serial console) = Down Down Enter.
time.sleep(2.5)
for k in ["down", "down", "ret"]:
    mon(f"sendkey {k}")
    time.sleep(0.3)
print("sent GRUB selection keys", flush=True)

sess = open(f"{T}/session.log", "wb", buffering=0)
buf = b""
def expect(pattern, timeout=420):
    global buf
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([mfd], [], [], 1)
        if r:
            try: data = os.read(mfd, 4096)
            except OSError: data = b""
            if data:
                buf += data; sess.write(data); os.write(1, data)
        if re.search(pattern, buf.decode(errors="replace")):
            return True
    return False

def send(line): os.write(mfd, line.encode() + b"\r")

print("=== waiting for serial login prompt ===", flush=True)
if not expect(r"login:"):
    print("!!! no login prompt on serial"); proc.kill(); sys.exit(1)
send("sam"); time.sleep(2); send("eeepc"); time.sleep(4)
for c in [
    "systemctl is-active ssh; systemctl is-enabled ssh",
    "journalctl -b -u ssh --no-pager 2>&1 | tail -8",
    "ss -tlnp 2>/dev/null | head; ip -br addr",
    "nmcli -t -f DEVICE,STATE,CONNECTION device 2>/dev/null",
    "free -m | head -2; swapon --show; echo DIAG_DONE",
]:
    send(c); time.sleep(6)
expect(r"DIAG_DONE", 120)

# also try ssh from host
r = subprocess.run(["ssh", "-p", "2229", "-o", "BatchMode=yes", "-o",
                    "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
                    "-i", f"{T}/testkey", "sam@127.0.0.1", "echo SSH_FROM_HOST_OK; uname -a"],
                   capture_output=True, text=True)
print("HOST_SSH_RC=", r.returncode, r.stdout.strip()[:300], r.stderr.strip()[:200], flush=True)
proc.terminate()
print("=== end ===")
