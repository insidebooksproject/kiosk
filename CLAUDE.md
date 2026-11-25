# ibp-kiosk

One Debian 13 image for every IBP volunteer machine. It boots into a
full-screen launcher with one tile per task (TDCJ Book Portal, IBP Requests,
Ship Individual, Ship Bulk, Ship Manual) and nothing else. Background and
rollout are in `docs/design.md`; how to build, install and run it is in
`README.md`. This file holds the layout and the contracts between the parts.
It supersedes `ibp-book-portal-kiosk` (in `../ibp-book-portal-kiosk`), whose
installer this one grew from.

## Layout and ownership

| Path | What |
|---|---|
| `build.sh` | Builds `build/ibp-kiosk-<hostname>.iso`: the current Debian netinst ISO plus an unattended install entry |
| `installer/` | Preseed, USB boot menu, `early.sh` (picks the disk), `late.sh` (runs `setup.sh` in the new system) |
| `setup.sh` | Turns a minimal Debian 13 into a station; rerunnable over SSH |
| `packages/*.txt` | Debian packages, one per line, `#` comments. `setup.sh` installs the union |
| `setup.d/NN-name.sh` | Steps `setup.sh` runs in order after copying `rootfs/` (POSIX sh, sourced with the variables below) |
| `rootfs/` | Files copied to `/`, laid out by absolute path |
| `profiles/<name>/` | `profile.conf` and `station.toml` for each station role |
| `launcher/` | The launcher, a Python package `ibp_kiosk` (PySide6) with tests |
| `test-vm.sh` | Installs and boots the image in QEMU |

## Contracts

### Names and paths on the installed system

- Config directory `/etc/ibp-kiosk/`: `station.toml`, `profile.conf`,
  `shippy.ini` (root:kiosk 0640), `log-upload.conf` (root 0600),
  `tailscale-authkey` (root 0600, deleted after use).
- shippy-gui reads and writes `config.ini` in its working directory:
  `/home/kiosk/.config/shippy-gui/config.ini` (kiosk 0600).
- Launcher code: `launcher/ibp_kiosk/` is copied to
  `/usr/local/lib/ibp-kiosk/ibp_kiosk/` and run with the system `python3` and
  Debian's PySide6 packages (no venv, no network needed to start it).
- Users: `ibp` (admin, sudo, SSH keys only, created by the installer) and
  `kiosk` (no password, autologin on tty1, runs the session).
- Everything this project installs is named `ibp-kiosk-*`.

### Commands (all in `/usr/local/bin`)

| Command | Does |
|---|---|
| `ibp-kiosk-session` | Started from the `kiosk` login on tty1; runs labwc, which starts the launcher |
| `ibp-kiosk-launcher` | Runs the launcher (`python3 -m ibp_kiosk`) |
| `ibp-kiosk-launcher home` | Tells the running launcher to close the current app and show the tiles. labwc binds the Super key to it |
| `ibp-kiosk-app portal` | Firefox, kiosk mode, on the TDCJ Book Portal, own profile |
| `ibp-kiosk-app requests` | Firefox, kiosk mode, on the IBP frontend, own profile |
| `ibp-kiosk-app ship-individual` / `ship-bulk` | shippy in a full-screen terminal |
| `ibp-kiosk-app ship-manual` | shippy-gui |
| `ibp-kiosk-app wifi` | `nmtui` in a terminal (admin screen) |
| `ibp-kiosk-app print-diag` | `ibp-print-diag` in a terminal that stays open until a key is pressed (admin screen) |
| `ibp-kiosk-status network\|server\|printer-shipping\|printer-package` | One status check: exit 0 = fine, non-zero = problem; first line of stdout is a short text for the volunteer |

`ibp-kiosk-app` runs in the foreground and exits when the app closes; its
exit status and its stderr/stdout are what the launcher shows on a failure.

### `/etc/ibp-kiosk/station.toml`

```toml
[station]
name = "Shipping 1"          # optional; default is the hostname
autostart = "ship-individual"  # optional tile id: started at boot; when
                             # it exits the launcher shows as usual

[[tile]]
id = "ship-individual"
label = "Ship Individual"
description = "One package to one person"     # optional, small text
command = ["ibp-kiosk-app", "ship-individual"]

[[status]]                   # status strip, left to right
label = "Label printer"
command = ["ibp-kiosk-status", "printer-shipping"]
interval = 15                # seconds between checks (default 15)

[[admin]]                    # admin screen entries, same keys as [[tile]]
id = "wifi"
label = "Wi-Fi"
command = ["ibp-kiosk-app", "wifi"]
```

The launcher is generic: it knows nothing about Firefox, shippy or printers.
It only runs these commands. Unknown keys are errors, and an `autostart` that
names no tile is an error (the launcher shows a config-error screen).

### Launcher behaviour the other parts rely on

- **Home.** The launcher holds a lock on
  `$XDG_RUNTIME_DIR/ibp-kiosk/launcher.pid`; `ibp-kiosk-launcher home` sends
  that pid SIGUSR1 and exits 0 if there is no launcher. labwc binds Super
  (either side, pressed alone) and F12 to it, so no app ever receives F12.
- **Admin screen:** Ctrl+Alt+A, only when the tiles are showing. labwc must
  not bind it.
- **Failure screen:** shown when an app exits non-zero or within 3 seconds,
  with its last 15 lines of output. `ibp-kiosk-app` must print a reason and
  exit non-zero when it can't start something.
- **Power commands** can be replaced with `IBP_KIOSK_POWEROFF` and
  `IBP_KIOSK_REBOOT` (for tests and the VM).
- Wayland app_id `ibp-kiosk-launcher`. labwc's config is in
  `/etc/ibp-kiosk/labwc/`; the launcher is labwc's session client (`-S`), so
  the session ends, and getty restarts it, if the launcher exits.

### `profile.conf`

Shell variables, sourced by `setup.sh` and `setup.d/*.sh`, installed as
`/etc/ibp-kiosk/profile.conf`:

```sh
KIOSK_PROFILE="shipping"     # the profile's name, so a rerun can find it
KIOSK_FEATURES="shipping"    # space-separated, see below
```

| Feature | Turns on |
|---|---|
| `shipping` | uv, shippy and shippy-gui config, the PM-2411-BT udev rule, `ibp-label-watcher` (user service), log upload timer |
| `package-printer` | CUPS and `ibp-print-server` (DYMO LabelWriter, `localhost:40121`) |
| `low-memory` | Firefox low-memory prefs (2 GB Chromebook) |

Profiles: `shipping` (all five tiles), `intake` (IBP Requests, plus
`package-printer`), `portal` (Book Portal only, `autostart`, `low-memory`).

### Variables `setup.sh` gives `setup.d/*.sh`

`KIOSK_SRC` (this repo's files on the target), `KIOSK_SECRETS` (secrets
directory, may be empty), `KIOSK_PROFILE`, `KIOSK_FEATURES`, `KIOSK_LIVE`
(1 on a running system, empty in the installer's chroot: only restart
services when it is set), and a function `has_feature NAME`. Steps must be
safe to rerun. `setup.sh [-p PROFILE] [SECRETS_DIR]`; without `-p` it reuses
the installed profile.

### Secrets directory (written by `build.sh`, every file optional)

`authorized_keys`, `wifi/*.nmconnection`, `tailscale-authkey`, `shippy.ini`,
`shippy-gui.ini`, `log-upload.conf` (`SHARE=//host/share`, `USERNAME=`,
`PASSWORD=`).

`build.sh` settings (environment, asked for when required and unset):
`KIOSK_PROFILE`, `KIOSK_HOSTNAME`, `KIOSK_WIFI_SSID`, `KIOSK_WIFI_PSK`,
`KIOSK_ADMIN_PASSWORD`, `KIOSK_SSH_KEYS`, `KIOSK_TAILSCALE_AUTHKEY`,
`KIOSK_SHIPPY_CONFIG`, `KIOSK_SHIPPY_GUI_CONFIG`, `KIOSK_LOG_SHARE`,
`KIOSK_LOG_USER`, `KIOSK_LOG_PASSWORD`.

## Rules

- Never commit secrets or anything under `build/`. The ISO holds the Wi-Fi
  password, API keys and the admin password hash.
- The installer erases a disk. `early.sh` installs only when exactly one
  internal (non-USB) disk is present, and the boot menu never starts on its
  own.
- Commits: one line, `tag: summary` (`feat`, `bugfix`, `docs`, `test`,
  `chore`, `refactor`), no attribution lines. Work on a feature branch in a
  worktree under `.claude/worktrees/`.
- Shell is POSIX `sh` on the target (`setup.sh`, `setup.d`, `rootfs` scripts)
  and passes `shellcheck`. `build.sh` and `test-vm.sh` may use bash.

## State

Built 2026-11-24. Nothing has been installed on real hardware.

Tested in the QEMU VM (`KIOSK_TEST=1 ./build.sh`, `./test-vm.sh install`,
`shipping` profile, dummy credentials, 4 GB): the unattended install onto an
NVMe disk; boot into the launcher; the Book Portal tile (reaches the ID.me
sign-in); Ship Individual and Ship Bulk (shippy in foot, reports no printer);
Ship Manual (shippy-gui maximized, its Settings dialog as a dialog); the Home
key (Super and F12); the admin screen and `nmtui`; the label watcher service;
the power button; a reboot; and the installer's refusal with two internal
disks (`./test-vm.sh install --two-disks`: it waits at partitioning and both
disks stay empty).

Not tested: any real hardware (PM-2411-BT and DYMO printers, Wi-Fi, the Acer
laptops, the Chromebook's 2 GB); the IBP Requests page itself (the server
isn't reachable from the VM); the `intake` and `portal` profiles; the print
server; log upload to the real share; Tailscale join. `docs/apps.md` has the
apps' own "Not verified" list and `docs/design.md` the rollout.

Known rough edges:
- A bad or missing Google Maps key makes shippy-gui exit with a Python
  traceback, which the launcher's failure screen shows as is.
- shippy's "no printer" text names the Windows folder `Downloads\to-print`.
- With QEMU's `virtio-vga`, terminal windows show stale frames; `test-vm.sh`
  uses a plain framebuffer. Not seen as a problem outside the VM, but check
  the terminal tiles first on real hardware.
- The repo is local only (no GitHub remote yet), so `../bootstrap.sh` doesn't
  clone it.
