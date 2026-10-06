#!/usr/bin/env python3
# 74-diskboot-screen.py — boot the raw image via BIOS/GRUB with VGA, screendump at intervals.
import subprocess, time, os, socket

BASE = "/var/lib/vz/eeepc"
T = "/tmp/eeepc-screen"
os.makedirs(T, exist_ok=True)
subprocess.run(["rm", "-f", f"{T}/disk.img", f"{T}/t.mon"], check=True)
subprocess.run(["cp", f"{BASE}/eeepc701-linux.img", f"{T}/disk.img"], check=True)

proc = subprocess.Popen([
    "qemu-system-x86_64", "-enable-kvm", "-cpu", "qemu32", "-m", "2048", "-smp", "1",
    "-drive", f"file={T}/disk.img,if=ide,format=raw",
    "-netdev", "user,id=n0,hostfwd=tcp:127.0.0.1:2229-:22",
    "-device", "e1000,netdev=n0",
    "-display", "none", "-vga", "std",
    "-monitor", f"unix:{T}/t.mon,server=on,wait=off",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def mon(cmd):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(f"{T}/t.mon")
    time.sleep(0.3)
    s.recv(4096)
    s.sendall((cmd + "\n").encode())
    time.sleep(0.8)
    try:
        out = s.recv(65536).decode(errors="replace")
    except socket.timeout:
        out = ""
    s.close()
    return out

for label, wait in [("early", 15), ("grub", 25), ("boot", 45), ("late", 60)]:
    time.sleep(wait)
    mon(f"screendump {T}/{label}.ppm")
    info = mon("info status")
    print(f"[{label}] {info.strip()}", flush=True)

proc.terminate()
print("dumps in", T)
