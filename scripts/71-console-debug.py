#!/usr/bin/env python3
# 71-console-debug.py — boot image, capture serial to FILE, type via monitor sendkey.
# Fully deterministic: file serial is proven; monitor sendkey needs no socket reads.
import subprocess, time, sys, os, re

BASE = "/var/lib/vz/eeepc"
VT = "/var/lib/vz/eeepc/vt"          # stable kernel/initrd extraction point
T = "/tmp/eeepc-console"
MON = f"{T}/mon.sock"
SERLOG = f"{T}/serial.log"

os.makedirs(T, exist_ok=True)
os.makedirs(VT, exist_ok=True)
os.makedirs("/mnt/dbg", exist_ok=True)

subprocess.run(["rm", "-f", f"{T}/disk.img", SERLOG, MON], check=True)
subprocess.run(["cp", f"{BASE}/eeepc701-linux.img", f"{T}/disk.img"], check=True)

loop = subprocess.check_output(["losetup", "--show", "-fP", f"{T}/disk.img"], text=True).strip()
subprocess.run(["mount", loop + "p1", "/mnt/dbg"], check=True)
# stable-extract kernel/initrd once (reused across runs)
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
    "-netdev", "user,id=n0,hostfwd=tcp:127.0.0.1:2226-:22",
    "-device", "e1000,netdev=n0",
    "-display", "none",
    "-serial", f"file:{SERLOG}",
    "-monitor", f"unix:{MON},server=on,wait=off",
])

def mon(cmd):
    subprocess.run(["socat", "-", f"UNIX-CONNECT:{MON}"], input=(cmd + "\n").encode(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)

KEYMAP = {}
for c in "abcdefghijklmnopqrstuvwxyz0123456789": KEYMAP[c] = c
KEYMAP.update({"-": "minus", "=": "equal", " ": "spc", "/": "slash", ".": "dot",
               ":": "shift-semicolon", "-": "minus", "_": "shift-minus", "|": "shift-backslash"})
def typestr(s):
    for ch in s:
        if ch in KEYMAP:
            mon(f"sendkey {KEYMAP[ch]}")
            time.sleep(0.12)
        elif ch == "\r":
            mon("sendkey ret"); time.sleep(0.3)

def wait_log(pattern, timeout):
    end = time.time() + timeout
    while time.time() < end:
        try:
            txt = open(SERLOG, errors="replace").read()
        except FileNotFoundError:
            txt = ""
        if re.search(pattern, txt):
            return True
        time.sleep(3)
    return False

print("waiting for boot...", flush=True)
if not wait_log(r"login:", 360):
    print("NO LOGIN PROMPT"); proc.kill(); sys.exit(1)
typestr("sam\r"); time.sleep(3)
typestr("eeepc\r"); time.sleep(4)
cmds = [
    "systemctl --no-pager status ssh.service 2>&1 | tail -15",
    "journalctl -b -u ssh.service --no-pager 2>&1 | tail -15",
    "ls -la /etc/ssh/ /run/sshd 2>&1",
    "/usr/sbin/sshd -t; echo SSDT=$?",
    "free -m; swapon --show",
    "echo DEBUG_DONE",
]
for c in cmds:
    typestr(c + "\r"); time.sleep(6)
wait_log(r"DEBUG_DONE", 120)
time.sleep(2)
print(open(SERLOG, errors="replace").read()[-6000:])
proc.terminate()
