# IBP station: one Debian image with a launcher for the IBP apps

Design, 2026-11-24. Status: proposal, nothing built. Facts about the current
machines come from `ops/shipping-laptops.md`, `ibp-book-portal-kiosk` and
`ibp-printing` as of this date; anything not yet tried is listed under
"To verify".

Every volunteer machine at IBP does one of five things. Today those run on
three differently built systems: two Windows shipping laptops, a Linux Mint
intake station, and a Debian Chromebook kiosk. This replaces them with one
Debian image that boots straight into a full-screen launcher with one big
tile per task, and nothing else: no desktop, no file manager, no settings.

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
| Ship Individual | `shippy individual` in a full-screen terminal |
| Ship Bulk | `shippy bulk` in a full-screen terminal |
| Ship Manual | `shippy-gui` |

Which tiles a machine shows is a per-machine setting, so the same image
serves each role:

| Station | Tiles |
|---|---|
| Shipping laptop | All six |
| Intake station | IBP Requests (plus the Book Portal if wanted) |
| Book Portal kiosk | TDCJ Book Portal only; with one tile the launcher is skipped and the app opens at boot, as now |

## Decisions

| | Decision |
|---|---|
| EasyPost in the browser | No tile for now (decided 2026-11-24). The laptops' EasyPost login shortcut is rarely used; add a tile later if it's needed |
| Intake station | Moves to this image eventually, after the shipping laptops (decided 2026-11-24) |

## Design

### Base system

The same base as `ibp-book-portal-kiosk`, which already works: Debian 13
minimal, `unattended-upgrades` with a 03:00 reboot, a `kiosk` user with no
password that logs in automatically on tty1, and the session started from
that login so that getty restarting it is the watchdog. Admin users (`ibp`,
`jstarr`, `emilliken`), OpenSSH with keys only, and Tailscale are set up as
on the kiosk and `ibp-server`.

### Session and compositor

The session runs a Wayland compositor with the launcher as its first client.
The launcher starts one app at a time as a child process and shows itself
again when the child exits.

Use **labwc** rather than cage. The kiosk uses cage, which is enough for one
app that never closes, but a multi-app station needs two things cage doesn't
have:

- **A Home key.** A full-screen terminal has no close button (Firefox has
  its own since 2026-11-25, when it stopped using kiosk mode). labwc can bind a key (Super, with a sticker on it) to a
  command that closes the running app and returns to the launcher.
- **Ordinary dialog handling.** shippy-gui opens a settings dialog and message
  boxes. labwc is a normal stacking compositor; window rules keep main
  windows maximized and undecorated.

If labwc proves troublesome, the fallback is cage with one compositor run per
app (a session loop: launcher, then the chosen app, then launcher again).

### Launcher

A small PySide6 program (`ibp-kiosk-launcher`), since PySide6 is already in use for
shippy-gui. It has:

- **Tiles**, read from `/etc/ibp-kiosk/station.toml` (which tiles, their
  labels and commands). Large text, keyboard and mouse both work.
- **A status strip**: network up, `ibp-server` reachable, label printer
  detected. This is what a volunteer reads out over the phone.
- **Power**: shut down and restart buttons.
- **An admin screen** behind a key combination: join Wi-Fi (`nmtui` in a
  terminal), run `ibp-print-diag`, show the machine's name and version.

It holds no credentials and makes no purchases; it only starts programs and
shows status. If an app exits within a few seconds, the launcher shows the
last lines of its output instead of silently returning to the tiles.

### The apps

- **Firefox** is `firefox-esr` with the kiosk's policy setup
  (`policies.json`: force-installed extension, lockdown, no saved passwords,
  DoH off so `ibp-server.local` resolves). Each browser tile uses its own
  profile and opens its page in an ordinary Firefox window (tabs, address
  bar, a close button), not `--kiosk`: volunteers close it like any browser
  and can open other tabs. The Book Portal login goes through ID.me, so
  any site allow-list must include it.
- **shippy** runs as today, with uvx from the `deploy` branch:
  `uvx --from git+https://github.com/jonkensta/shippy.git@deploy shippy --config /etc/ibp-kiosk/shippy.ini bulk|individual`,
  inside a terminal (foot) with a large font. When shippy exits, the terminal
  closes and the launcher returns.
- **shippy-gui** runs with uvx from `deploy`, from a working directory that
  holds its `config.ini` (it reads the file from the current directory).
- The apps are installed as uv tools for the `kiosk` user and upgraded from
  `deploy` at each launch. If the upgrade fails (no internet), the installed
  version starts. uvx's offline mode can't do this: tested with uv 0.12.9, it
  refuses anything that comes from a git branch or tag, even when cached
  (`docs/apps.md`).

### Printing

- **Shipping labels (PM-2411-BT, BOB and BETTY).** `ibp-printing` talks to the
  printer directly over USB through `usblp` (`/dev/usb/lpN`), with no vendor
  driver and no CUPS queue. This path was verified on real hardware under
  Linux on 2026-10-04 (`ibp-printing/docs/printers/pm2411bt.md`). The image
  installs `packaging/linux/60-ibp-label-printer.rules` so the `kiosk` user
  can open the device.
- **Package labels (DYMO LabelWriter 450 Turbo).** The image includes CUPS and
  `ibp-print-server` as a systemd unit, as on `ibp-label-printer` today. The
  unit is enabled only on stations that have the tile and the printer.
- **Label watcher.** `ibp-label-watcher` runs as a systemd user service for
  the `kiosk` user, retrying labels the apps could not print. It replaces the
  "IBP Label Watcher" scheduled task.

### Configuration and secrets

`config.ini` for shippy and shippy-gui holds the IBP, EasyPost and Google Maps
API keys. As with the kiosk, `build.sh` pulls them from Bitwarden into the
installer stick at build time and `setup.sh` installs them readable by the
`kiosk` user only. They are never committed, and the stick is wiped after
use. The Wi-Fi profiles are handled the same way.

### Logs

The apps already write to `~/.local/state/ibp-printing/logs` on Linux. A
systemd timer copies that directory to the machine's own Samba share on
`ibp-server` every 15 minutes, replacing the "IBP Log Upload" task. The share
password is in a root-only credentials file.

### Power

Lid close and the power button shut the machine down, and it never suspends
on AC. `ibp-label-printer` showed why: a closed lid suspended it and the
print server needed a resume hook. USB autosuspend is turned off for the
label printers.

### Where the code lives

A new repo, `ibp-kiosk`, with the launcher, the session files, and the
installer taken over from `ibp-book-portal-kiosk` (`build.sh`, `setup.sh`,
`rootfs/`, `test-vm.sh`). The kiosk repo stays as it is until the Chromebook
is reinstalled from the new image, then is archived.

The installer needs one change before it can be used on a laptop:
`installer/early.sh` only installs to an `mmcblk` disk. It needs a target
rule per machine type that still refuses to touch any disk it doesn't
expect.

## Rollout

1. **Live USB check on `ibp-laptop2`** (nothing installed, Windows untouched):
   Wi-Fi, a PM-2411-BT test print with `ibp-print-diag --test-print
   --direct-only`, the barcode scanner, and `shippy diagnose-printer`. If the
   printer or the Wi-Fi fails here, stop.
2. **Launcher and session in a VM**, using `test-vm.sh`.
3. **Installer image**, tested by reinstalling the Chromebook kiosk with the
   one-tile profile.
4. **Convert `ibp-laptop2`.** Before wiping it, copy off `config.ini` and the
   logs and take a disk image. `ibp-laptop` stays on Windows for a few
   shipping sessions as the fallback.
5. **Convert `ibp-laptop`.**
6. **Move the intake station** (`ibp-label-printer`) to the image.

Steps 4 to 6 erase the machine's current install (Windows on the laptops,
Linux Mint on the intake station) and can't be undone without a disk image
taken first.

## To verify

- The Acer Aspire A315-24P under Debian 13: Wi-Fi, graphics, lid and power
  button behaviour.
- shippy-gui (PySide6) under labwc: main window, dialogs, font scaling.
- labwc is packaged in Debian 13 at a version with the key bindings and
  window rules used here.
- `ibp-label-watcher` printing on Linux. Its docs describe Linux as a
  development setup, so real printing from the watcher is untested.
- The launcher plus Firefox within the Chromebook's 2 GB of RAM. Firefox
  alone used about 840 MB.

## Open questions

- **Host names.** The convention is decided (2026-11-25): `ibp-<name>` with
  a Tolkien character, instead of `ibp-laptop` and `ibp-laptop2`. Which
  machine gets which name, and their log shares, are settled before step 4.
- **Home key.** Super is the proposal; whether volunteers find it is a
  question for the first on-site session.
