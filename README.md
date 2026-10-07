# Deeebian
*Debian for the Eee PC.*

A purpose-built 32-bit Linux distribution for the **ASUS Eee PC 701 4G** (2007 netbook:
Celeron M ULV 353 @ 900 MHz, Intel 915GM graphics, Atheros AR5007EG wifi, 2 GB RAM).

## What it is

- **Base:** Debian 12 (bookworm) i386 userland — still fully security-supported
- **Kernel:** vanilla **6.12 LTS compiled for i386, non-PAE** (CONFIG_HIGHMEM4G) with all
  701 hardware drivers **built into the kernel** (ata_piix, usb-storage, uhci/ehci,
  ath5k, atl2, snd-hda-intel, i915, eeepc-laptop). The non-PAE kernel boots on both
  PAE and non-PAE steppings of this CPU, so there is no CPUID guessing.
- **Desktop:** Openbox + tint2 + pcmanfm + lxterminal, lightdm autologin (user `sam`)
- **Memory:** runs comfortably in 2 GB — zram swap (1 GB, lz4) instead of disk swap,
  so the SD card is never written for swapping
- **SD-friendly:** ext4 with `noatime,commit=60`, /tmp on tmpfs, journald capped at 30 MB

## Download

Prebuilt image, release **v1.0.0**:

- <https://github.com/GodSpoon/eeepc701-linux/releases/tag/v1.0.0>
- `eeepc701-linux.img.xz` (~610 MB) + `.sha256` sidecar

## Flashing

```bash
# find your SD card first (be sure!): lsblk
xz -dc eeepc701-linux.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
```

Or use balenaEtcher / Raspberry Pi Imager with the `.img.xz` file directly.

Then on the 701: power on, tap **F2** → *Boot* → set the **SD card reader as the first
boot device** (the BIOS treats the internal reader as a mass-storage/USB device) — or tap
**Esc** at POST for the one-time boot menu and pick the SD card.

First boot automatically grows the root filesystem to fill the card.

## Login

| Account | Password |
|---|---|
| `sam` | `eeepc` (has sudo — change with `passwd`) |
| root | locked (use sudo) |

## Networking

- Wifi: click the **nm-applet** icon in the panel (top right), pick your network.
- Ethernet (Attansic L2) works out of the box via NetworkManager.
- SSH server is on: `ssh sam@eeepc701.local` (avahi/mDNS).

## Cheat sheet

| Task | How |
|---|---|
| Menu | right-click desktop, or Super+D |
| Terminal | Super+Enter |
| Browser | Super+F (Firefox ESR; Netsurf is installed for very light pages) |
| Volume | Fn+F12 / volume icon; mixer: `alsamixer` |
| File manager | `pcmanfm` |
| Suspend | `systemctl suspend` |
| Update | `sudo apt update && sudo apt upgrade` |

## Hardware support matrix (701-specific)

| Component | Driver | Status |
|---|---|---|
| CPU Celeron M ULV 353 | — | non-PAE kernel, works on all steppings |
| GPU Intel 915GM (800×480 LVDS) | i915 | native panel resolution |
| Wifi Atheros AR5007EG | ath5k | built-in, no firmware blob |
| Ethernet Attansic/Atheros L2 | atl2 | built-in |
| Audio Realtek ALC662 | snd-hda-intel | auto-unmuted on boot |
| SD card reader (USB) | usb-storage | bootable from BIOS |
| Webcam | uvcvideo | module in kernel |
| Fn keys / fan | eeepc-laptop | loaded at boot |

## Rebuilding from source

See `scripts/` — order: `10-packages.sh`, `20-kernel.sh`, `30-configure.sh`,
`90-cleanup.sh` (all inside an i386 bookworm debootstrap chroot with the kernel
tree bind-mounted at `/build`), then `40-image.sh` and `50-vmtest.sh` on the build host.
