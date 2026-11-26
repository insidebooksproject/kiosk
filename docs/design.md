# IBP station: one Debian image with a launcher for the IBP apps

Design, 2026-11-24, with the decisions made while building it (2026-11-24
and 25). This is the why and the plan; what was built is in `README.md`,
`CLAUDE.md` and `docs/apps.md`, and where they differ from this, they are
right. Facts about the current machines come from the IBP workspace's
`ops/shipping-laptops.md`, the predecessor `ibp-book-portal-kiosk` and the
printing repo as of 2026-11-24.

Every volunteer machine at IBP does one of a handful of things. Today those
run on three differently built systems: two Windows shipping laptops, a
Linux Mint intake station, and a Debian Chromebook running the Book Portal
in a Firefox kiosk. This replaces them with one Debian image that boots
straight into a full-screen launcher with one big tile per task, and nothing
else: no desktop, no file manager, no settings.

## Goals

- A volunteer turns the machine on and picks a task. Nothing to log in to,
  nothing else to click.
- One image and one installer for every station. A dead machine is replaced
  by a USB reinstall, not by an afternoon of setup.
- No Windows upkeep: no OneDrive desktop, scheduled tasks, power-plan tuning
  or PowerShell over `cmd.exe`.
- The apps themselves don't change. They are still released by
  fast-forwarding each repo's `deploy` branch.

Not goals: a general-purpose desktop, changing the shipping workflow, or
moving the server.

## Tiles

| Tile | What runs |
|---|---|
| TDCJ Book Portal | Firefox on `https://bookportal.tdcj.texas.gov/BookPortal/` with the IBP extension |
| IBP Requests | Firefox on the IBP frontend on `ibp-server` |
| IBP Packages | Firefox on the IBP frontend's packages page (record the books in a package) |
| Ship Individual | `shippy individual` in a terminal |
| Ship Bulk | `shippy bulk` in a terminal |
| Ship Manual | `shippy-gui` |

Which tiles a machine shows is a per-machine setting, its profile, so the
same image serves each role: the shipping laptops get all six, the intake
station IBP Requests, and the Chromebook the Book Portal alone, opened at
boot (`README.md`, "Profiles").

## Decisions

| | Decision |
|---|---|
| EasyPost in the browser | No tile for now (decided 2026-11-24). The laptops' EasyPost login shortcut is rarely used; add a tile later if it's needed |
| Intake station | Moves to this image eventually, after the shipping laptops (decided 2026-11-24) |
| Firefox | An ordinary window with tabs and a close button, not kiosk mode (2026-11-25): volunteers close it like any browser and can open other tabs |
| Terminal tiles | A title bar that names the mode and has a large close button (2026-11-25), so the screen always says whether it is Ship Individual or Ship Bulk |
| Updates of the station itself | Each station runs `setup.sh` from this repo's `deploy` branch at boot (2026-11-25), released like the apps; the repo is public so no credential is needed |
| Host names | `ibp-<name>` with a Tolkien character (2026-11-25), instead of `ibp-laptop` and `ibp-laptop2` |

## Design

### Base system

The predecessor's base, which already worked: Debian 13 minimal,
`unattended-upgrades` with a 03:00 reboot, a `kiosk` user with no password
that logs in automatically on tty1, and the session started from that login
so that getty restarting it is the watchdog. OpenSSH with keys only, and
Tailscale. One admin user, `ibp` (the design proposed `jstarr` and
`emilliken` as well; the build has only `ibp`, with the keys from
`KIOSK_SSH_KEYS`).

### Session and compositor

The session runs a Wayland compositor with the launcher as its first client.
The launcher starts one app at a time as a child process and shows itself
again when the child exits.

**labwc**, not cage. The predecessor used cage, which is enough for one app
that never closes, but a multi-app station needs:

- **A Home key.** labwc binds a key (Super, with a sticker on it)
  to a command that closes the running app and returns to the launcher.
- **Title bars where they help.** labwc is a normal stacking compositor:
  window rules keep main windows maximized and undecorated, give the
  terminal tiles and Ship Manual a title bar with a close button, and leave
  shippy-gui's settings dialog and message boxes as ordinary dialogs.

The fallback, had labwc failed, was cage with one compositor run per app (a
session loop: launcher, then the chosen app, then launcher again).

### Launcher

A small PySide6 program (`ibp-kiosk-launcher`), since PySide6 is already in
use for shippy-gui: the tiles from `/etc/ibp-kiosk/station.toml`, a status
strip a volunteer can read out over the phone (network, server, printer,
updates), shut down and restart buttons, and an admin screen behind a key
combination (Wi-Fi, `ibp-print-diag`, the machine's name and version). It
holds no credentials and makes no purchases; it only starts programs and
shows status. If an app fails or exits within a few seconds, it shows the
last lines of the app's output instead of silently returning to the tiles.

### The apps

- **Firefox** is Debian's `firefox-esr` with the predecessor's
  `policies.json` (force-installed extension, lockdown, no saved passwords,
  DoH off so `ibp-server.local` resolves). Each browser tile has its own
  profile. The Book Portal login goes through ID.me, so any site allow-list
  must include it.
- **shippy** and **shippy-gui** come from their `deploy` branches, as on the
  laptops, but as uv tools for the `kiosk` user, upgraded at each launch
  rather than run with `uvx`: if the upgrade fails (no internet) the
  installed version starts. `uvx --offline` can't do that; tested with uv
  0.12.9, it refuses anything from a git branch or tag, even when cached
  (`docs/apps.md`). shippy runs in a terminal (foot) with a large font;
  shippy-gui runs from a working directory that holds its `config.ini` (it
  reads the file from the current directory).

### Printing

- **Shipping labels (PM-2411-BT, BOB and BETTY).** ibp-printing talks to the
  printer directly over USB through `usblp` (`/dev/usb/lpN`), with no vendor
  driver and no CUPS queue. This path was verified on real hardware under
  Linux on 2026-10-04 (the printing repo's `docs/printers/pm2411bt.md`). The
  image's own udev rule lets the `kiosk` user open the device (a group, not
  the upstream rule's `uaccess`; `docs/apps.md` says why).
- **Package labels (DYMO LabelWriter 450 Turbo).** CUPS and
  `ibp-print-server` as a systemd unit, as on `ibp-label-printer` today,
  only on stations with feature `package-printer` (the intake profile).
- **Label watcher.** `ibp-label-watcher` runs as a systemd user service for
  the `kiosk` user, retrying labels the apps could not print. It replaces the
  "IBP Label Watcher" scheduled task.

### Configuration and secrets

`config.ini` for shippy and shippy-gui holds the IBP, EasyPost and Google Maps
API keys. `build.sh` copies them, and the Wi-Fi profiles, onto the installer
stick at build time and `setup.sh` installs them readable by the `kiosk`
user only. They are never committed, and the stick is wiped after use.

### Logs

The apps already write to `~/.local/state/ibp-printing/logs` on Linux. A
systemd timer copies that directory to the machine's own Samba share on
`ibp-server` every 15 minutes, replacing the "IBP Log Upload" task. The share
password is in a root-only credentials file.

### Power

Lid close and the power button shut the machine down, and it never suspends.
`ibp-label-printer` showed why: a closed lid suspended it and the print
server needed a resume hook. USB autosuspend is turned off for the label
printers.

### Where the code lives

This repo, with the installer taken over from `ibp-book-portal-kiosk`
(`build.sh`, `setup.sh`, `rootfs/`, `test-vm.sh`). That repo was archived on
2026-11-25; the Chromebook keeps its old install until it is reinstalled
from this image. The installer's disk rule changed on the way: the
predecessor's `early.sh` installed only to an `mmcblk` disk, this one to the
one internal disk of any kind, and refuses when there isn't exactly one.

## Rollout

1. **Live USB check on `ibp-laptop2`** (nothing installed, Windows untouched):
   Wi-Fi, a PM-2411-BT test print with `ibp-print-diag --test-print
   --direct-only`, the barcode scanner, and `shippy diagnose-printer`. If the
   printer or the Wi-Fi fails here, stop.
2. **Launcher and session in a VM**, using `test-vm.sh`. Done 2026-11-24.
3. **Installer image**, tested by reinstalling the Chromebook kiosk with the
   `portal` profile.
4. **Convert `ibp-laptop2`.** Before wiping it, copy off `config.ini` and the
   logs and take a disk image. `ibp-laptop` stays on Windows for a few
   shipping sessions as the fallback.
5. **Convert `ibp-laptop`.**
6. **Move the intake station** (`ibp-label-printer`) to the image.

Steps 4 to 6 erase the machine's current install (Windows on the laptops,
Linux Mint on the intake station) and can't be undone without a disk image
taken first. The first hardware trial, outside this list, is the MacBook
`ibp-bilbo` (`CLAUDE.md`, "Machines").

## To verify

- The Acer Aspire A315-24P under Debian 13: Wi-Fi, graphics, lid and power
  button behaviour.
- shippy-gui (PySide6) font scaling on the laptops. Its main window and
  dialogs work under labwc in the VM.
- `ibp-label-watcher` printing on Linux. Its docs describe Linux as a
  development setup, so real printing from the watcher is untested.
- The launcher plus Firefox within the Chromebook's 2 GB of RAM. Firefox
  alone used about 840 MB.

`docs/apps.md` lists what is untested in the apps themselves.

## Open questions

- **Host names.** Which machine gets which name, and their log shares, are
  settled before step 4.
- **Home key.** Whether volunteers find Super is a question for the first
  on-site session.
