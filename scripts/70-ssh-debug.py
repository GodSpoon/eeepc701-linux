#!/usr/bin/env python3
# 70-ssh-debug.py v2 — boots image in KVM, serial console over TCP, logs in, dumps ssh/zram state.
import subprocess, time, sys, os, re, socket

BASE = "/var/lib/vz/eeepc"
T = "/tmp/eeepc-sshdbg"
SERIAL_PORT = 4441
SSH_PORT = 2225

subprocess.run(["mkdir", "-p", T, "/mnt/dbg"], check=True)
subprocess.run(["rm", "-f", f"{T}/disk.img"], check=True)
subprocess.run(["cp", f"{BASE}/eeepc701-linux.img", f"{T}/disk.img"], check=True)

# extract kernel/initrd and inject test ssh key in one mount
loop = subprocess.check_output(["losetup", "--show", "-fP", f"{T}/disk.img"], text=True).strip()
subprocess.run(["mount", loop + "p1", "/mnt/dbg"], check=True)
k = [f for f in os.listdir("/mnt/dbg/boot") if f.startswith("vmlinuz-")][0]
i = [f for f in os.listdir("/mnt/dbg/boot") if f.startswith("initrd.img-")][0]
subprocess.run(["cp", f"/mnt/dbg/boot/{k}", f"{T}/vmlinuz"], check=True)
subprocess.run(["cp", f"/mnt/dbg/boot/{i}", f"{T}/initrd.img"], check=True)
subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", f"{T}/testkey", "-q"], check=True)
os.makedirs("/mnt/dbg/home/sam/.ssh", exist_ok=True)
open("/mnt/dbg/home/sam/.ssh/authorized_keys", "w").write(open(f"{T}/testkey.pub").read())
subprocess.run(["chown", "-R", "1000:1000", "/mnt/dbg/home/sam/.ssh"], check=True)
subprocess.run(["umount", "/mnt/dbg"], check=True)
subprocess.run(["losetup", "-d", loop], check=True)

qemu_err = open(f"{T}/qemu.err", "w")
proc = subprocess.Popen([
    "qemu-system-x86_64", "-enable-kvm", "-cpu", "qemu32", "-m", "2048", "-smp", "1",
    "-kernel", f"{T}/vmlinuz", "-initrd", f"{T}/initrd.img",
    "-append", "root=UUID=b0057a11-de12-b007-01ee-000000000001 ro console=ttyS0,115200n8",
    "-drive", f"file={T}/disk.img,if=ide,format=raw",
    "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{SSH_PORT}-:22",
    "-device", "e1000,netdev=n0",
    "-display", "none",
    "-serial", f"tcp:127.0.0.1:{SERIAL_PORT},server=on,wait=off",
    "-monitor", f"unix:{T}/mon.sock,server=on,wait=off",
], stderr=qemu_err)

s = None
for _ in range(90):
    try:
        s = socket.create_connection(("127.0.0.1", SERIAL_PORT), timeout=5)
        break
    except OSError:
        time.sleep(2)
if s is None:
    print("NO SERIAL TCP"); print(open(f"{T}/qemu.err").read()); proc.kill(); sys.exit(1)
s.settimeout(5)
buf = b""

def expect(pattern, timeout=300):
    global buf
    end = time.time() + timeout
    while time.time() < end:
        try:
            data = s.recv(4096)
            if data:
                buf += data
                sys.stdout.write(data.decode(errors="replace")); sys.stdout.flush()
        except socket.timeout:
            pass
        if re.search(pattern, buf.decode(errors="replace")):
            return True
    return False

def send(line):
    s.sendall(line.encode() + b"\r")

print("=== waiting for login prompt ===")
if not expect(r"login:"):
    print("!!! no login prompt"); proc.kill(); sys.exit(1)
send("sam"); time.sleep(2); send("eeepc"); time.sleep(3)
for cmd in [
    "systemctl --no-pager --full status ssh.service 2>&1 | tail -20",
    "journalctl -b -u ssh.service --no-pager 2>&1 | tail -20",
    "ls -la /etc/ssh/ /run/sshd 2>&1",
    "/usr/sbin/sshd -t 2>&1; echo SSD_T_EXIT=$?",
    "systemctl --no-pager status zram-swap.service 2>&1 | tail -8",
    "free -m; swapon --show; echo DEBUG_DONE",
]:
    send(cmd); time.sleep(4)
expect(r"DEBUG_DONE", 90)
proc.terminate()
print("\n=== debug session end ===")
