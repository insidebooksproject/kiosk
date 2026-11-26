# ibp-kiosk

One Debian 13 image for every IBP volunteer machine. It boots into a
full-screen launcher with one tile per task (TDCJ Book Portal, IBP Requests,
IBP Packages, Ship Individual, Ship Bulk, Ship Manual) and nothing else. The
repo is `insidebooksproject/kiosk` (public); the product, and everything it
installs, is named `ibp-kiosk`. Build, install and run it: `README.md`. The
apps, printers and status checks: `docs/apps.md`. Why it is built this way,
and the rollout: `docs/design.md`. The launcher: `launcher/README.md`. This
file: the layout, the contracts between the parts, releasing, and the
machines.

It replaces `jonkensta/ibp-book-portal-kiosk` (the Chromebook's Firefox
kiosk; archived 2026-11-25, not moved to the organisation), whose installer
this one grew from.

## Layout and ownership

| Path | What |
|---|---|
| `build.sh` | Builds `build/ibp-kiosk-<hostname>.iso`: the current Debian netinst ISO plus an unattended install entry and `/kiosk/payload.cpio.gz` (preseed, this repo, secrets) |
| `installer/` | Preseed, USB boot menu, `early.sh` (picks the disk), `late.sh` (runs `setup.sh` in the new system) |
| `setup.sh` | Turns a minimal Debian 13 into a station: installs `packages/*.txt`, copies `rootfs/`, the launcher and the profile, creates the `kiosk` user, then sources `setup.d/*.sh` in order. Rerunnable |
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
  `tailscale-authkey` (root 0600, deleted after use), `update.conf`
  (optional, 0644: `UPDATE_BRANCH`, `UPDATE_URL`), `apps.conf` (optional,
  never installed: start-page and server URLs, `docs/apps.md`), and from
  `rootfs/` `foot.ini` and `labwc/`.
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
| `ibp-kiosk-launcher home` | Tells the running launcher to close the current app and show the tiles. labwc binds Super to it |
| `ibp-kiosk-app portal` | Firefox on the TDCJ Book Portal, own profile: an ordinary window with tabs (not kiosk mode) whose close button returns to the tiles |
| `ibp-kiosk-app requests` | The same on the IBP frontend, own profile |
| `ibp-kiosk-app packages` | The same on the IBP frontend's packages page (`/packages`), in the `requests` profile |
| `ibp-kiosk-app ship-individual` / `ship-bulk` | shippy in a maximized terminal whose title bar names the mode and has a close button |
| `ibp-kiosk-app ship-manual` | shippy-gui, with the same title bar ("Ship Manual") |
| `ibp-kiosk-app wifi` | `nmtui` in the same kind of terminal (admin screen) |
| `ibp-kiosk-app print-diag` | `ibp-print-diag` in the same kind of terminal, open until a key is pressed (admin screen) |
| `ibp-kiosk-tool TOOL COMMAND` | Installs or upgrades shippy, shippy-gui or ibp-printing from its `deploy` branch as a uv tool, then runs COMMAND (`docs/apps.md`) |
| `ibp-kiosk-log-upload` | Copies the label-printer logs to the station's Samba share; run by `ibp-kiosk-log-upload.timer` |
| `ibp-kiosk-update` | Run as root by `ibp-kiosk-update.service` at boot: when the `deploy` branch of this repo has moved, clones it and runs its `setup.sh`; state in `/var/lib/ibp-kiosk/update` (`commit`, `src`, `status`) |
| `ibp-kiosk-status network\|server\|printer-shipping\|printer-package\|update\|battery` | One status check: exit 0 = fine, non-zero = problem; first line of stdout is a short text for the volunteer (`battery` prints nothing on a machine with no battery) |

`ibp-kiosk-app` runs in the foreground and exits when the app closes; its
exit status and its stderr/stdout are what the launcher shows on a failure.
Once their app has run, the terminal tiles exit 0 whatever it did: an error
stays on the terminal's screen until a key is pressed, so the launcher's
failure screen would add nothing.

### `/etc/ibp-kiosk/station.toml`

```toml
[station]
name = "Shipping 1"          # optional; default is the hostname
autostart = "ship-individual"  # optional tile id: started at boot; when
                             # it exits the launcher shows as usual

[[tile]]
id = "ship-individual"
label = "Ship Individual"
description = "Mail a package to one inmate"   # optional, small text
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
  (either side, pressed alone) to it.
- **Admin screen:** Ctrl+Alt+A, only when no app is running. labwc must not
  bind it.
- **Failure screen:** shown when an app exits non-zero or within 3 seconds,
  unless the launcher stopped it (Home key), with its last 15 lines of
  output. `ibp-kiosk-app` must print a reason and exit non-zero when it
  can't start something.
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
| `package-printer` | uv, CUPS and `ibp-print-server` (DYMO LabelWriter, `localhost:40121`) |
| `low-memory` | Firefox low-memory prefs (2 GB Chromebook) |

The profiles and their tiles: `README.md`, "Profiles".

### Variables `setup.sh` gives `setup.d/*.sh`

`KIOSK_SRC` (this repo's files on the target), `KIOSK_SECRETS` (secrets
directory, may be empty), `KIOSK_PROFILE`, `KIOSK_FEATURES`, `KIOSK_LIVE`
(1 on a running system, empty in the installer's chroot: only restart
services when it is set), and a function `has_feature NAME`. Steps must be
safe to rerun and must not call `exit`. `setup.sh [-p PROFILE]
[SECRETS_DIR]`; without `-p` it reuses the installed profile.

### Secrets directory (written by `build.sh`, every file optional)

`authorized_keys`, `wifi/*.nmconnection` (`ibp-wifi`, `ibp-site-wifi`),
`tailscale-authkey`, `update.conf` (`UPDATE_BRANCH=`; not a secret, it rides
along), `shippy.ini`, `shippy-gui.ini`, `log-upload.conf`
(`SHARE=//host/share`, `USERNAME=`, `PASSWORD=`), `force-broadcom-sta`
(empty; test builds only). A rerun without a secrets directory leaves the
installed ones alone. `build.sh`'s settings are in `README.md`, step 1.

## Releasing

The repo is public (since 2026-11-25) so stations can fetch it without a
credential: nothing secret goes in it, in any commit. Every station that
follows `deploy` (the default) runs that branch's `setup.sh` as root at its
next boot, so a broken `deploy` breaks every station. Release like the apps:
merge into `main`, try it in the VM (`UPDATE_URL` in the VM's
`/etc/ibp-kiosk/update.conf` can point at a local clone), then fast-forward
`deploy` to `main` (`git push origin main:deploy`). `setup.sh` and every
`setup.d` step must stay safe to rerun on a live station with no secrets
directory, and must not restart the session. A failed run keeps the old
commit recorded and is retried at the next boot.

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

Built 2026-11-24. The only install on real hardware, on the MacBook
`ibp-bilbo`, is not trustworthy (see Machines).

Tested in the QEMU VM (`KIOSK_TEST=1 ./build.sh`, `./test-vm.sh install`,
`shipping` profile, dummy credentials, 4 GB): the unattended install onto an
NVMe disk; boot into the launcher; the Book Portal tile (reaches the ID.me
sign-in); Ship Individual and Ship Bulk (shippy in foot, reports no printer);
Ship Manual (shippy-gui maximized, its Settings dialog as a dialog); the Home
key (Super); the admin screen and `nmtui`; the label watcher service; the
power button; a reboot; and the installer's refusal with two internal
disks (`./test-vm.sh install --two-disks`: it waits at partitioning and both
disks stay empty). That run predates the 2026-11-25 changes (Firefox as an
ordinary window, the title bars, the IBP Packages tile, the status chips,
the boot updater); this file records no test of them. The Battery chip
(2026-11-26) was tested with the launcher's tests, against fake sysfs trees
and by running the check on `ibp-bilbo` on mains power ("Plugged in (86%)");
its estimate on battery has not been seen on real hardware.

Tested in the VM 2026-11-26 (Firefox ESR 153.7): Firefox forgets a
volunteer's cookies, site storage and history after a clean close, after
SIGTERM (what the Home key sends) and after SIGKILL, and the next start's
first request carries no old cookie; the extension's storage is unchanged;
the Book Portal tile still reaches the ID.me sign-in.

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

## Machines

Host names are `ibp-<name>`, where the name is a Tolkien character (decided
2026-11-25): short, easy to spell aloud, no villains (`ibp-frodo`,
`ibp-pippin`, `ibp-merry`, `ibp-gimli`). The name belongs to the hardware and
stays when the profile changes; the role volunteers see is `name` in
`station.toml`.

Every kiosk machine joins the **IBP tailnet** (GitHub organisation
`insidebooksproject`, set up 2026-11-25), never jstarr's personal one. Build
with `KIOSK_TAILSCALE_AUTHKEY` set to the hidden field `auth-key-station` of
Bitwarden `tailscale insidebooksproject`: it tags the machine
`tag:ibp-station`, which may reach the server on tcp 80 and 445 only. Don't
sign a station in interactively: an untagged machine belongs to the person
and gets admin access. The move of the existing hosts is in the IBP
workspace's `BACKLOG.md` (the `meta` repo).

### MacBook `ibp-bilbo` (model A1278)

Reinstalled from the stick 2026-11-25 and checked over SSH
(`ibp@ibp-bilbo.local`): `product_name` is `MacBookPro9,2`, Ethernet and
Wi-Fi are both up, it joined the IBP tailnet as `ibp-bilbo`, and the boot
updater brought it to the current `deploy`. It is at jstarr's home, where
neither the server's LAN address nor its tailnet address (still the personal
tailnet) is reachable, so the IBP server chip says "Not reachable" until
`ibp-server` moves to the IBP tailnet (the workspace's `BACKLOG.md`).
shippy-gui's config on the machine has the real Google Maps key (Bitwarden
`Google Maps API (IBP)`, set by hand 2026-11-25); its IBP and EasyPost keys
and all of shippy's are still placeholders.

Closing the lid shuts it down (checked 2026-11-26). Not yet checked on it:
the label printer and the Broadcom driver step's log. The stick still holds
the Wi-Fi passwords, the Tailscale key and the admin password hash.

The stick (the 14.6 GB USB flash drive, rewritten 2026-11-25 from `main` at
`685e362`): profile `shipping`, hostname `ibp-bilbo` (the first stick, and
the 2026-11-24 install, called the machine `ibp-april`); Wi-Fi profiles
`ibp-wifi` (home 2.4 GHz, Bitwarden `Home WIFI 2.4G`) and `ibp-site-wifi`
(Bitwarden `IBP WIFI`); the `ibp` admin password is Bitwarden `ibp-kiosk`;
the IBP tailnet's station key, so it joins as `ibp-bilbo` on first boot. It
updates itself from `deploy` at boot. shippy and shippy-gui have
**placeholder** configs (no real API keys): the shipping tiles open but
can't look up requests or buy postage. No log share.

The disk: the internal SSD (Patriot P210 128GB) was not usable: link CRC
errors at 6 Gbps and no IDENTIFY at lower speeds, coming and going with
reseating the flex cable and with the bottom cover on or off.
`libata.force=` options (`nologdir`, `1.5Gbps`, `noncq`) did not get around
it. After a reseat one install went through (2026-11-24) and boots into the
launcher, so the installer, boot, Intel graphics and labwc work on it. That
install is not trustworthy: the Network check says "could not run", sshd
resets every connection before its banner, and Ctrl+Option+(fn)+F2 did not
reach a console (it does in the VM). Files damaged by the bad link is the
likely cause, never confirmed (no shell access). Don't debug it; reinstall
after the cable.

The model: the serial's model code (DTY3) reads as the 13-inch Mid 2012
MacBook Pro (MacBookPro9,2: Intel HD 4000 graphics, Intel SATA and xHCI,
matching the installer's logs); confirm with
`cat /sys/class/dmi/id/product_name` (confirmed 2026-11-25). RAM and Wi-Fi
chip are still unknown.
The Broadcom `wl` driver step (`setup.d/30-broadcom.sh`) built in the VM
with `KIOSK_TEST_BROADCOM_STA=1` but has not run on the hardware.
