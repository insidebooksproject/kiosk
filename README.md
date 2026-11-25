# ibp-kiosk

One Debian 13 (trixie) image for every IBP volunteer machine. It boots
straight into a full-screen launcher with a big tile per task (TDCJ Book
Portal, IBP Requests, Ship Individual, Ship Bulk, Ship Manual) and nothing
else: no desktop, no file manager, no settings. Background is in
[`docs/design.md`](docs/design.md); the layout and the contracts between the
parts are in [`CLAUDE.md`](CLAUDE.md).

- **Debian 13**, minimal. Security updates install themselves
  (`unattended-upgrades`) and the machine reboots at 03:00 when one needs it.
- **labwc** (a small Wayland compositor) runs the launcher. The `kiosk` user
  is logged in automatically on tty1; if the session ends or crashes, the
  login ends and a fresh one starts it again.
- **Profiles** decide what a machine shows and installs: `shipping`,
  `intake` or `portal` (see [Profiles](#profiles)).
- Admin: the `ibp` user (sudo) over SSH (keys only), on the console
  (Ctrl+Alt+F2), and optionally on the tailnet.

## 1. Build the USB stick

Build one ISO per machine; the profile and the hostname are baked in.

```sh
KIOSK_PROFILE=shipping KIOSK_HOSTNAME=ibp-laptop2 ./build.sh
```

It asks for anything required and unset:

| Setting | |
|---|---|
| `KIOSK_PROFILE` | `shipping`, `intake` or `portal` |
| `KIOSK_HOSTNAME` | the machine's name (lowercase, digits, dashes); by convention `ibp-` plus a Tolkien character, e.g. `ibp-pippin` |
| `KIOSK_WIFI_SSID`, `KIOSK_WIFI_PSK` | Wi-Fi (WPA2 personal), used by the installer and the station. Empty SSID: no Wi-Fi, and the install needs an Ethernet cable |
| `KIOSK_ADMIN_PASSWORD` | password for `ibp` (sudo, console) |
| `KIOSK_SSH_KEYS` | `authorized_keys` for `ibp`; default `~/.ssh/id_ed25519.pub` |
| `KIOSK_TAILSCALE_AUTHKEY` | optional auth key: joins the tailnet as the hostname on first boot, then the key file is deleted. Use the IBP tailnet's station key (Bitwarden `tailscale insidebooksproject`, field `auth-key-station`) |
| `KIOSK_SHIPPY_CONFIG`, `KIOSK_SHIPPY_GUI_CONFIG` | shipping only: the `config.ini` files for shippy and shippy-gui |
| `KIOSK_LOG_SHARE`, `KIOSK_LOG_USER`, `KIOSK_LOG_PASSWORD` | shipping only: the machine's Samba log share on ibp-server (`//host/share`) |

For the shipping settings an empty answer leaves that file out; it can be
added later by rerunning `setup.sh` with a secrets directory.

The ISO holds the Wi-Fi password, the API keys and the admin password hash:
`build/` is gitignored, and wipe the stick after use. The Debian ISO is
checked against Debian's signed checksums and reused from `build/` while it
is current. Write the ISO (this erases the stick):

```sh
sudo dd if=build/ibp-kiosk-ibp-laptop2.iso of=/dev/sdX bs=4M conv=fsync status=progress
```

`KIOSK_TEST=1 ./build.sh` builds a test ISO with no real secrets (admin
password `testpw`, no Wi-Fi, placeholder app configs, profile `shipping`,
hostname `test-station`, all overridable). Never install it on a real
machine.

## 2. Install

UEFI machines only. Boot the stick (Acer: F12 at power-on, after enabling
the F12 boot menu in the firmware setup; Chromebook: Esc with MrChromebox
firmware) and choose **Install IBP station _name_ (_profile_)**. The menu
names the machine the stick was built for and waits for Enter, so a machine
that boots it by accident never starts an install. The rest is unattended
(20-30 minutes) and ends with a reboot; pull the stick.

- It installs to the one internal disk (NVMe, SATA or eMMC) and stops
  without touching anything unless there is exactly one. USB disks and
  removable cards don't count. It wipes that disk: GPT, EFI and one ext4
  root, no swap partition (zram instead).
- When it refuses (no internal disk found, or more than one), it stays at
  the partitioning step forever rather than show a dialog, because
  continuing past a dialog would let the installer pick a disk itself.
  Alt+F4 shows the reason; hold the power button to turn the machine off.
  Unplug any other internal or card storage and start again.
- Network: a plugged-in Ethernet cable wins; otherwise the build's Wi-Fi.
- If it stops on a question (usually the network), answer it and it carries
  on. The log is `/var/log/installer/syslog` on the installed machine.

### On a MacBook

Needs a 64-bit Intel MacBook (Core 2 Duo or later; not a T2 or Apple Silicon
one). The 13-inch A1278 (2008-2012) is the one this was written for.

1. Plug in power, the stick and **an Ethernet cable**. The installer has no
   driver for the Broadcom Wi-Fi in these machines, so it installs over the
   wire even when the stick was built with Wi-Fi. `setup.d/30-broadcom.sh`
   then installs the driver (`broadcom-sta-dkms`, Broadcom's `wl`, for the
   older chips; `firmware-brcm80211` for the newer ones), and the saved
   Wi-Fi profiles work from the first boot.
2. Hold **Option** and press the power button. Keep holding until the boot
   picker appears, choose **EFI Boot** (the orange USB icon), then the
   install entry.
3. When it reboots, pull the stick. Once the launcher's Network chip shows
   a connection, unplug the cable and check it changes to the Wi-Fi's name.

On a Mac keyboard the Home key is **Command**. The function keys need
**fn**: Home is also fn+F12, the admin console is Ctrl+Option+fn+F2 and back
is Ctrl+Option+fn+F1. The admin screen is Ctrl+Option+A.

If the screen stays black after the install (the 2008-2010 models have
Nvidia graphics, driven by nouveau), log in over SSH and add
`WLR_RENDERER=pixman` to `/etc/ibp-kiosk/labwc/environment`, then
`sudo systemctl restart getty@tty1`.

## Running it

- **Off/on:** closing the lid or pressing the power button shuts down
  cleanly; it never suspends. The power button starts it again.
- **Closing the browser:** Firefox is an ordinary window with tabs; its
  close button (top right) returns to the tiles.
- **Home key:** the Windows (Super) key on its own, or F12, closes the
  current app and shows the tiles. On the Chromebook it is the Search key.
- **Admin console:** Ctrl+Alt+F2, log in as `ibp`. Ctrl+Alt+F1 returns to
  the station.
- **SSH:** `ssh ibp@<hostname>.local` on the LAN, or `<hostname>` on the
  tailnet. To join the IBP tailnet by hand, use the station key, not a
  browser sign-in: `sudo tailscale up --hostname=$(hostname) --auth-key=<key>`.
- **Restart the session:** `sudo systemctl restart getty@tty1`.
- **Logs:** `journalctl -t ibp-kiosk` (labwc, the launcher and the apps).
- **Wi-Fi:** the launcher's admin screen has a Wi-Fi entry (`nmtui`); from
  the console, `sudo nmtui`.
- **Change the setup:** edit this repo, copy it over and rerun `setup.sh`
  (it keeps the machine's profile; `-p NAME` switches it):

  ```sh
  rsync -a --exclude build --exclude .git ./ ibp@<hostname>.local:ibp-kiosk/
  ssh -t ibp@<hostname>.local sudo sh ibp-kiosk/setup.sh [-p PROFILE] [SECRETS_DIR]
  ```

  `SECRETS_DIR` is optional and holds the same files `build.sh` writes
  (`authorized_keys`, `wifi/*.nmconnection`, `tailscale-authkey`,
  `shippy.ini`, `shippy-gui.ini`, `log-upload.conf`). Without it the
  installed secrets are left as they are.

## Profiles

| Profile | Tiles | Features |
|---|---|---|
| `shipping` | Ship Individual, Ship Bulk, Ship Manual, TDCJ Book Portal, IBP Requests | `shipping`: shippy, shippy-gui, the PM-2411-BT label printer, log upload |
| `intake` | IBP Requests | `package-printer`: CUPS and the DYMO print server |
| `portal` | TDCJ Book Portal, opened at boot | `low-memory`: Firefox settings for the 2 GB Chromebook |

Each is `profiles/<name>/profile.conf` (installed as
`/etc/ibp-kiosk/profile.conf`) and `station.toml` (the tiles, status strip
and admin screen, installed as `/etc/ibp-kiosk/station.toml`).

## How it fits together

| Path | What |
|---|---|
| `build.sh` | Builds the ISO: Debian netinst plus `/kiosk/payload.cpio.gz` (preseed, this repo, secrets) and a boot menu |
| `installer/` | `preseed.cfg`, the USB boot menu `grub.cfg`, `early.sh` (picks the disk), `late.sh` (runs `setup.sh` in the new system) |
| `setup.sh` | Installs `packages/*.txt`, copies `rootfs/` to `/`, the launcher to `/usr/local/lib/ibp-kiosk`, the profile to `/etc/ibp-kiosk`, creates the `kiosk` user, then sources `setup.d/*.sh` in order |
| `rootfs/` | Config files, laid out by absolute path |
| `test-vm.sh` | Installs and boots the image in QEMU |

The session: getty logs `kiosk` in on tty1, its `~/.bash_profile` runs
`ibp-kiosk-session`, which runs
`labwc -C /etc/ibp-kiosk/labwc -S ibp-kiosk-launcher`. labwc reads only that
directory: `rc.xml` (main windows maximized without decorations, dialogs
keep a title bar with a close button; the Home key; no menus, desktops or
other default bindings), `environment` and `autostart` (a dark
background). When the launcher exits, labwc exits and getty starts over.

## Testing in a VM

Needs `qemu-system-x86` and `ovmf`.

```sh
KIOSK_TEST=1 ./build.sh
./test-vm.sh install            # 4 GB of RAM; --mem 2G for the Chromebook
```

Press Enter at the boot menu (VNC on `localhost:5901`, or
`./test-vm.sh monitor 'sendkey ret'`). The VM disk is NVMe, the network
wired. QEMU exits when the installer reboots; then `./test-vm.sh` boots the
installed system. SSH: `/usr/bin/ssh -p 2222 ibp@localhost`. Other monitor
commands: `./test-vm.sh monitor 'sendkey meta_l'` (the Home key),
`./test-vm.sh monitor 'screendump build/vm/screen.ppm'`; by hand,
`echo 'info status' | nc -U -q 1 build/vm/monitor.sock`.
