# The apps on an IBP station

How each tile's app runs, where its config and logs are, how the printers are
set up, and what has not been tried yet. The contract between the launcher,
the base system and the apps is in `CLAUDE.md`; the background is in
`docs/design.md`.

## Files

| Path (in the repo) | What |
|---|---|
| `rootfs/usr/local/bin/ibp-kiosk-app` | Starts one tile's app (below) |
| `rootfs/usr/local/bin/ibp-kiosk-status` | The status strip's checks |
| `rootfs/usr/local/bin/ibp-kiosk-tool` | Installs, upgrades and runs shippy, shippy-gui and ibp-printing as uv tools |
| `rootfs/usr/local/bin/ibp-kiosk-log-upload` | Copies the label-printer logs to the Samba share |
| `rootfs/usr/share/firefox-esr/distribution/policies.json` | Firefox policies (both browser tiles) |
| `rootfs/etc/firefox-esr/ibp-kiosk.js` | Firefox prefs (both browser tiles) |
| `rootfs/etc/gtk-3.0/settings.ini` | Firefox's window buttons: close only |
| `rootfs/usr/local/share/ibp-kiosk/firefox/ibp-kiosk-low-memory.js` | Low-memory prefs, copied to `/etc/firefox-esr/` with feature `low-memory` |
| `rootfs/etc/ibp-kiosk/foot.ini` | The terminal's config |
| `rootfs/etc/uv/uv.toml` | uv: Debian's Python only, never download one |
| `rootfs/etc/polkit-1/rules.d/50-ibp-kiosk-network.rules` | Lets `kiosk` change network settings (Wi-Fi tile) |
| `rootfs/usr/local/share/ibp-kiosk/udev/*.rules` | Printer udev rules, copied to `/etc/udev/rules.d/` per feature |
| `rootfs/etc/systemd/user/ibp-kiosk-label-watcher.service` | The label watcher, a `kiosk` user service |
| `rootfs/etc/systemd/system/ibp-kiosk-log-upload.{service,timer}` | Log upload every 15 minutes |
| `rootfs/etc/systemd/system/ibp-kiosk-print-server{,-update}.service` | ibp-print-server and its update from GitHub |
| `setup.d/50-apps.sh` | Low-memory prefs; git and uv for features `shipping` and `package-printer` |
| `setup.d/60-shipping.sh` | Feature `shipping` |
| `setup.d/70-package-printer.sh` | Feature `package-printer` |
| `packages/apps.txt` | Debian packages every station gets |

## Tiles

| `ibp-kiosk-app` | Runs |
|---|---|
| `portal` | `firefox-esr --no-remote --profile ~/.local/share/ibp-kiosk/firefox/portal --name ibp-kiosk-portal https://bookportal.tdcj.texas.gov/BookPortal/protected/dashboard.action` |
| `requests` | the same with profile `requests`, app_id `ibp-kiosk-requests`, on `http://192.168.1.156/` |
| `packages` | the same as `requests` (same profile and app_id), on `http://192.168.1.156/packages` |
| `ship-individual`, `ship-bulk` | `foot --fullscreen` running `shippy --config /etc/ibp-kiosk/shippy.ini individual` / `bulk` |
| `ship-manual` | `shippy-gui`, from `/home/kiosk/.config/shippy-gui` (it reads `config.ini` from its working directory) |
| `wifi` | `foot --fullscreen` running `nmtui` |
| `print-diag` | `foot --fullscreen` running `ibp-print-diag`, then "press any key" |

`ibp-kiosk-app` stays in the foreground (it `exec`s the app, so the launcher's
SIGTERM to the process group reaches the app itself) and exits with the
app's status. When something is missing it prints one line on stderr and
exits 1 (2 for a bad argument), e.g. "Shipping is not set up on this machine:
/etc/ibp-kiosk/shippy.ini is missing or not readable. Ask an IBP admin."
It checks, before starting anything: the shippy config (ship tiles),
shippy-gui's `config.ini` (Ship Manual), `firefox-esr`, `foot`, `nmtui` and
`/usr/local/bin/uv`.

The start pages can be changed without editing the script: an optional
`/etc/ibp-kiosk/apps.conf` (shell syntax, not installed by default) may set
`PORTAL_URL`, `REQUESTS_URL`, `PACKAGES_URL` (default: `/packages` under
`REQUESTS_URL`) and, for `ibp-kiosk-status server`,
`IBP_SERVER_URL` (default `http://192.168.1.156`).

### Browser tiles

- **URLs.** The portal's is the predecessor's start page
  (`ibp-book-portal-kiosk`'s `policies.json`), which sends a signed-out
  volunteer to the login (ID.me). The IBP frontend's is the "App" address in
  `ops/ibp-server.md` (ibp-meta): `http://192.168.1.156/`, LAN and tailnet
  only, the same server address `shippy`'s `sample.ini` uses. The Pi's LAN
  address is static. (`http://ibp-server.local/` also works where mDNS does;
  the extension uses that name.)
- **One `policies.json` for both.** Firefox reads policies system-wide, so
  both tiles get the predecessor's lockdown (no about:config, dev tools,
  other add-ons or saved passwords; DoH off so `ibp-server.local` resolves)
  and the force-installed IBP Book Portal Scanner extension. The predecessor's
  locked `Homepage` policy is gone: each tile's start page is passed on the
  command line and written to its profile's `user.js` (for Alt+Home).
  Added: `DisableProfileRefresh` and `DisableSafeMode`, so repeated unclean
  exits never offer a refresh or safe mode.
- **The extension in the requests profile.** It is installed there too
  (policies can't differ per profile) and is harmless: its content scripts
  match only `https://bookportal.tdcj.texas.gov/BookPortal/protected/*` and
  its two test hosts (`manifest.json`), its background script only answers
  messages from those pages, and on install it only clears old storage keys.
  In the requests profile it does nothing but take a little memory. Each
  profile downloads it once, on its first start with network.
- **Home key, crashes, power cuts.** The launcher ends an app with SIGTERM to
  its process group and SIGKILL 5 s later. `ibp-kiosk.js` makes every start
  plain: `browser.startup.page` 1 (the tile's page),
  `browser.sessionstore.resume_from_crash` false (no "restore session" page),
  `toolkit.startup.max_resumed_crashes` -1 (no safe-mode offer), no crash
  report prompts, no quit or close warnings. `MOZ_CRASHREPORTER_DISABLE=1` is
  set too. If a Firefox for the same profile is still running at start (its
  pid from the profile's `lock` link, checked against its command line), the
  wrapper waits 10 s for it, then ends it, so the new one never says
  "Firefox is already running".
- **Print server from IBP Requests.** The frontend posts labels from
  `http://192.168.1.156/` to `http://localhost:40121`. Firefox ESR 153's local
  network access checks skip private-to-localhost requests by default
  (`network.lna.local-network-to-localhost.skip-checks`); `ibp-kiosk.js` locks
  that to true.
- **Low memory** (feature `low-memory`, the 2 GB Chromebook): one content
  process, no fission, no bfcache, as on the predecessor. `50-apps.sh` copies
  `ibp-kiosk-low-memory.js` to `/etc/firefox-esr/` or removes it.

### shippy, shippy-gui and ibp-printing: `ibp-kiosk-tool`

The laptops run the apps with `uvx --from git+...@deploy` at every launch.
That has no offline fallback, so the station uses persistent `uv tool`
installs instead, in the `kiosk` user's home:

```
ibp-kiosk-tool [--no-upgrade | --install-only] TOOL [COMMAND [ARG...]]
```

1. If TOOL isn't installed: `uv tool install SPEC` (needs the network).
2. Otherwise: `uv tool upgrade NAME`, with a 90 s timeout. A tool installed
   from a branch re-resolves the branch, so this picks up whatever `deploy`
   points at now. If it fails ("Could not check for updates (no
   internet?)"), the installed version starts anyway.
3. `exec ~/.local/bin/COMMAND`.

| TOOL | SPEC | Used by |
|---|---|---|
| `shippy` | `shippy @ git+https://github.com/jonkensta/shippy.git@deploy` | Ship Individual, Ship Bulk |
| `shippy-gui` | `shippy-gui @ git+https://github.com/jonkensta/shippy-gui.git@deploy` | Ship Manual |
| `ibp-printing` | `ibp-printing[watcher] @ git+https://github.com/jonkensta/ibp-printing.git@deploy` | label watcher, Printer check (`--no-upgrade`) |
| `ibp-printing-server` | `ibp-printing[linux] @ ...@deploy` | the print server (user `ibp-kiosk-print`) |

Releasing stays as it is: fast-forward `deploy`; stations pick it up at the
next launch (the watcher and print server at their next start, i.e. boot).
A changed SPEC in this script (recorded in
`~/.local/state/ibp-kiosk/tools/TOOL.spec`) reinstalls the tool. A lock
(`flock`) keeps two installs of one tool apart. `setup.d` preinstalls every
tool the station's features need (as its user), so the first launch is quick
and works offline; if that fails at install time, the first launch installs
it instead (shippy-gui's PySide6 is about 700 MB, so that takes minutes with
no window showing).

**uv's offline mode, as observed** (uv 0.12.9 on this build machine,
2026-11-24; network "down" simulated with an unreachable `https_proxy`):

| Command | Result |
|---|---|
| `uvx --from git+https://github.com/jonkensta/shippy.git@deploy shippy --help`, cold cache | works, 3.4 s |
| same, warm cache | works, 0.7 s (still fetches the branch) |
| same with `--offline`, warm cache, network up | fails at once: "failed to fetch branch or tag `deploy`: Remote Git fetches are not allowed because network connectivity is disabled (i.e., with `--offline`)" |
| `uvx --offline --from git+...shippy.git@<commit sha>`, warm cache for that sha | fails the same way, on shippy's own dependency `ibp-printing @ git+...@v0.4.0`: uv must fetch a tag too |
| any of these online with the network down | fails after 4 to 8 s (uv's retries) |
| `uv tool install git+...shippy.git@deploy`, then network down: `uv tool upgrade shippy` | fails after about 7 s; the installed `~/.local/bin/shippy` still runs |
| `uv tool upgrade` after a new commit on the branch (local test repo) | installs the new commit |

So `uvx --offline` cannot start anything from a git branch or tag, cached or
not; the design's "retry with uv's offline mode" would never work. A tool
install, upgraded at launch, is the offline fallback.

**uv itself.** Debian 13 has no `uv` package (it is only in unstable, as of
2026-11-24). `50-apps.sh` installs Astral's static build
(`uv-x86_64-unknown-linux-gnu.tar.gz`, pinned version and SHA-256 in the
script) to `/usr/local/bin/uv` and `uvx`, on stations with feature `shipping`
or `package-printer`, plus Debian's `git` (uv fetches git sources with it).
To update uv, bump `IBP_APPS_UV_VERSION` and the two checksums (from the
release's `.sha256` files) and rerun `setup.sh`; `uv self update` is not used.
`/etc/uv/uv.toml` (and `ibp-kiosk-tool`) set `python-preference =
"only-system"` and `python-downloads = "never"`: every tool runs on Debian's
`/usr/bin/python3` (3.13; shippy and shippy-gui need >= 3.12), which Debian
keeps patched.

Repair: an upgrade cut off half-way (a power cut, or the Home key during "Checking for
updates", which stops the upgrade too) could leave a tool broken. Delete its spec stamp and
the next launch reinstalls it, e.g.
`sudo rm /home/kiosk/.local/state/ibp-kiosk/tools/shippy.spec`.

Disk: uv's cache (`/home/kiosk/.cache/uv`) keeps old builds. Trim it now and
then with `sudo -u kiosk -H uv cache prune`.

### Ship Individual, Ship Bulk (foot)

`foot --config=/etc/ibp-kiosk/foot.ini --app-id=ibp-kiosk-ship-individual
--fullscreen -- ibp-kiosk-app --in-terminal ship-individual`. Inside, shippy
runs through `ibp-kiosk-tool` (so the update check is visible on screen). The
terminal closes when shippy exits 0 or 130 (130 is an unhandled Ctrl+C;
shippy's own "Press Ctrl+C to quit" at the no-printer prompt exits 1 today,
so it gets the message below). After any other non-zero exit the screen says
"shippy stopped (exit status N). Read the message above, then press any key
to close." Keys typed before that message (a scanner's Enter) are discarded
first, and the status goes to the journal (`ibp-kiosk-app`). Either way the
launcher then shows the tiles, not its failure screen: the volunteer has
already read the error where it was printed. foot runs with
`--log-level=error`, so its own warnings never show up as the reason an app
stopped. The Home key closes it at any time.

`foot.ini`: DejaVu Sans Mono 16 pt (about 150 x 45 on a 1920x1080 screen),
10000 lines of scrollback, and no key that starts another program (no new
terminal window, no URL launcher).

### Ship Manual (shippy-gui)

Runs from `/home/kiosk/.config/shippy-gui` with `QT_QPA_PLATFORM=wayland;xcb`.
Its Settings dialog writes `config.ini` there; `60-shipping.sh` never
overwrites that unless a *different* `shippy-gui.ini` secret is supplied
(the last one's checksum is in `/var/lib/ibp-kiosk/shippy-gui.ini.sha256`),
and then keeps the old file as `config.ini.bak-<date>`.

**No `linux` extra.** `shippy-gui[linux]` pulls `ibp-printing[linux]`, i.e.
pycups, which only exists on PyPI as a source tarball (pycups 2.0.4, no
wheels), so installing it needs `build-essential`, `python3-dev` and
`libcups2-dev` on the station. The shipping printers (PM-2411-BT) print over
direct USB through usblp, with no CUPS at all; pycups is only for CUPS
queues' default media size. Without pycups, ibp-printing falls back to
`lpstat`/`lp` for queues. The shipping stations get `cups-client` (no CUPS
daemon) only so that `lpstat` exists and `ibp-print-diag` reports no queues
instead of an error.

The PyPI PySide6 wheels bring their own Qt but load system libraries (EGL,
GL, fontconfig, freetype, D-Bus, GLib, xkbcommon, Wayland client, XCB);
`60-shipping.sh` installs them.

### Wi-Fi (nmtui) and polkit

`kiosk` has no password and no sudo. NetworkManager asks polkit, and
`/etc/polkit-1/rules.d/50-ibp-kiosk-network.rules` answers yes for `kiosk` in
the active local session (the tty1 session the launcher runs in) for these
actions only: `network-control`, `enable-disable-network`,
`enable-disable-wifi`, `wifi.scan`, `settings.modify.own`,
`settings.modify.system`. Not the hostname, sleep, global DNS, reload or
checkpoints. Side effect: whoever is at the station can read the saved Wi-Fi
passwords in nmtui's "Edit a connection".

### Printer check

`ibp-print-diag` (full report, no test print) from the `ibp-printing` tool,
without an upgrade, then "Done (exit status N). Press any key to close." On a
station without feature `shipping` the tool installs itself on first use.

## Status checks (`ibp-kiosk-status`)

Every external call has a timeout; the slowest case is about 6 s. The
launcher's strip shows only a mark and the check's label; the text is the
chip's tooltip, after the label ("IBP server: Not reachable"), so the texts
don't repeat the label.

| Check | How | Texts |
|---|---|---|
| `network` | `nmcli -t -f TYPE,STATE device`, the SSID from `nmcli device wifi list --rescan no`, `nmcli networking connectivity` | "Wi-Fi Vesper", "Cable", "Wi-Fi Vesper, but no internet" (connectivity none/limited/portal), "Not connected" |
| `server` | `GET http://192.168.1.156/api/health` (3 s connect, 4 s total) | "OK", "Not reachable", "Database problem" (503), "Error (N)" |
| `printer-shipping` | sysfs only: each `/sys/class/usbmisc/lp*` whose `device/ieee1284_id` has `MDL:PM2411BT` (or `MODEL:`, any case) or whose USB device is `2e3c:5760`; then whether `/dev/usb/lpN` exists and is read-write for the caller (`access()`, no open). Falls back to `/sys/bus/usb/devices` for a printer not bound to usblp | "Ready (BOB)" / "(BETTY)" by serial, "Plugged in, but not allowed (udev rule missing?)", "Plugged in, but not detected (try replugging it)", "Not plugged in" |
| `printer-package` | `GET http://localhost:40121/health` (the print server's own discovery: a usable label printer queue) | "Ready", "Not plugged in", "Problem (see the print server log)", "Print server not running" |

`printer-shipping` never opens the device: usblp allows one open, and
shippy or the watcher may be printing. Reading `ieee1284_id` returns the ID
usblp cached when the printer was plugged in.

## Shipping printer (PM-2411-BT)

`/etc/udev/rules.d/60-ibp-kiosk-label-printer.rules` (feature `shipping`):

- `/dev/usb/lpN` of USB vendor `2e3c` gets group `kiosk`, mode 0660. The
  upstream rule (`ibp-printing/packaging/linux/60-ibp-label-printer.rules`)
  uses `TAG+="uaccess"` instead, which follows the active seat: an admin
  logging in on another VT would take the printer away from the label
  watcher. The group works whatever session is in front.
- USB autosuspend off (`power/control=on`) for `2e3c:5760`.

## Label watcher

`ibp-kiosk-label-watcher.service` in `/etc/systemd/user`, enabled with
`systemctl --global enable` and limited by `ConditionUser=kiosk`, so it runs
in the kiosk user's manager from the autologin on, and never for an admin's
SSH login. It runs `ibp-kiosk-tool ibp-printing ibp-label-watcher` (upgrade
from `deploy` at each start, `Restart=on-failure` after 30 s).

What the code does on Linux (ibp-printing `deploy`, d4635f0):

- It prints. The watcher prints through the same backend as the apps
  (`DirectFirstBackend`: the PM-2411-BT over usblp first, then CUPS queues),
  which is the path verified on real hardware on 2026-10-04. Nothing in
  the watcher is Windows-only except message boxes.
- No message boxes: `notify.message_box` returns without showing anything
  off Windows. Everything it would say is only in
  `printer-watcher.log` and the journal.
- It watches `~/Downloads` (the fallback off Windows) and retries
  `~/Downloads/to-print`, which is where shippy and shippy-gui save labels
  they couldn't print (same library, same user, same folder).
- The single-instance lock and the label journal are in
  `~/.local/state/ibp-printing/`.

So printing from the watcher is expected to work but is still untested on a
real printer (see below).

## Log upload

`ibp-kiosk-log-upload.timer` (2 minutes after boot, then every 15 minutes)
starts `ibp-kiosk-log-upload.service`, which runs
`/usr/local/bin/ibp-kiosk-log-upload` as root. Both units have
`ConditionPathExists=/etc/ibp-kiosk/log-upload.conf`, and `60-shipping.sh`
enables the timer only when that file exists (installed from the secret
`log-upload.conf`, root 0600):

```
SHARE=//100.119.68.125/ibp-logs-<station>
USERNAME=ibplogs-<station>
PASSWORD=...
```

The script reads the file (never sources it; one pair of quotes around a
value is removed), writes a mount.cifs credentials file in the service's
root-only runtime directory, mounts the share in the service's private mount
namespace (`PrivateMounts=yes`, so it never outlives the service), deletes
the credentials file, and runs `rsync -rt --modify-window=2` (no `--delete`)
from `/home/kiosk/.local/state/ibp-printing/logs/` to `<share>/<hostname>/`.
The password is never on a command line. The host-named folder keeps a
station that reuses an old laptop's share from overwriting that laptop's
Windows logs (same file names). Each station still needs its own share and
account on ibp-server (`ops/ibp-server.md`, "Samba shares").

Run it now: `sudo systemctl start ibp-kiosk-log-upload`; result:
`journalctl -u ibp-kiosk-log-upload -n 20`.

## Package printer (DYMO) and ibp-print-server

Feature `package-printer`, `70-package-printer.sh`:

- Installs `cups cups-client cups-filters printer-driver-dymo`, and
  `build-essential python3-dev libcups2-dev` to build pycups.
- Creates the system user `ibp-kiosk-print` (home `/var/lib/ibp-kiosk-print`)
  and preinstalls `ibp-printing[linux]` from `deploy` as that user.
- Enables `cups` and `ibp-kiosk-print-server.service`, which runs
  `ibp-print-server server` (port 40121) as `ibp-kiosk-print`. Its `Wants=`
  starts `ibp-kiosk-print-server-update.service` first (`uv tool upgrade`,
  as upstream's `ExecStartPre`), so every boot picks up `deploy`; if that
  fails the installed version starts. The server unit allows only loopback
  traffic (`IPAddressDeny=any`, `IPAddressAllow=localhost`): the server
  listens on every interface, but only this machine's browser needs it.
  That is why the update is a separate unit.
- Why a service user and not `kiosk` or the admin: the Home key can't touch
  it, it has its own tool install with the `linux` extra, and an admin
  account isn't needed (upstream runs it as `ibp`, the intake station's
  login).
- USB autosuspend off for DYMO devices (vendor `0922`).
- No resume unit: the stations shut down on lid close.

**On site, once per station: the DYMO queue.** The print server only uses a
queue whose name ends in the printer's USB `VID:PID`
(`ibp-printing` README, "Printer naming rule"), and fits the label to the
queue's default page size. As `ibp` (sudo), with the printer plugged in:

```sh
lsusb | grep -i dymo                 # "ID 0922:xxxx Dymo-CoStar Corp. LabelWriter 450 Turbo"
lpinfo -v | grep -i dymo             # the device URI, usb://DYMO/LabelWriter%20450%20Turbo?serial=...
lpinfo -m | grep -i '450 Turbo'      # the driver's model name for -m
sudo lpadmin -p DYMO_LabelWriter_450_Turbo_0922:xxxx -E \
    -v 'usb://DYMO/LabelWriter%20450%20Turbo?serial=...' \
    -m '<model from lpinfo -m>' \
    -o PageSize=w102h252
```

`w102h252` is "30321 Large Address" (1.4 x 3.5 in), the label the
print-server docs size for (420 x 1050 px). If the intake station uses
another roll, copy its size: `lpoptions -p <queue> -l | grep PageSize` on
`ibp-label-printer` shows the current default (marked `*`). Then check,
without and with a print:

```sh
curl -s localhost:40121/health        # "count": 1
ibp-kiosk-status printer-package      # Ready
sudo -u ibp-kiosk-print -H /var/lib/ibp-kiosk-print/.local/bin/ibp-print-server list
sudo -u ibp-kiosk-print -H /var/lib/ibp-kiosk-print/.local/bin/ibp-print-server test   # prints a test label
```

## Where things are on a station

| What | Where |
|---|---|
| shippy config | `/etc/ibp-kiosk/shippy.ini` (root:kiosk 0640) |
| shippy-gui config | `/home/kiosk/.config/shippy-gui/config.ini` (kiosk 0600) |
| Log upload config | `/etc/ibp-kiosk/log-upload.conf` (root 0600) |
| Optional URL overrides | `/etc/ibp-kiosk/apps.conf` |
| Firefox profiles | `/home/kiosk/.local/share/ibp-kiosk/firefox/{portal,requests}` |
| Installed apps (uv tools) | `/home/kiosk/.local/share/uv/tools`, commands in `/home/kiosk/.local/bin`, cache `/home/kiosk/.cache/uv`; print server: the same under `/var/lib/ibp-kiosk-print` |
| shippy, shippy-gui, watcher, diag logs | `/home/kiosk/.local/state/ibp-printing/logs/printer-{shippy,shippy-gui,watcher,diag}.{log,jsonl}` |
| Label journal, watcher state | `/home/kiosk/.local/state/ibp-printing/` |
| Labels waiting to print | `/home/kiosk/Downloads/to-print/` (`printed/`, `check-printer/` next to it) |
| Watcher journal | `sudo journalctl _SYSTEMD_USER_UNIT=ibp-kiosk-label-watcher.service` |
| Print server | `journalctl -u ibp-kiosk-print-server`; `/var/lib/ibp-kiosk-print/.local/state/ibp-printing/logs/printer-print-server.log` |
| Log upload | `journalctl -u ibp-kiosk-log-upload` |

## Tested and not verified

Tested on the build machine (Pop!_OS, uv 0.12.9) on 2026-11-24:

- `shellcheck` and `sh -n` (dash) on every script and `setup.d` step.
- `ibp-kiosk-status network` (real NetworkManager: "Connected to Wi-Fi
  ..."), `server` (real: "IBP server not reachable" after 3 s, off the IBP
  LAN; against a local fake `/api/health`: OK, 404, unreachable),
  `printer-package` against a fake `/health` (ready, count 0, degraded, not
  running), `printer-shipping` against a fake sysfs tree (no printer, DYMO
  only, PM2411BT without node, without access, ready as BOB and BETTY,
  model by 1284 `MODEL:` in lower case, plugged in but not bound to usblp).
- `ibp-kiosk-app` argument handling (usage, exit 2), each tile's command
  line (`IBP_KIOSK_DRY_RUN=1`), the missing-config and missing-program
  errors, the in-terminal exit status and key pause in a pty (early key
  discarded), the wait for a previous Firefox on the profile (ended after
  10 s; an unrelated pid left alone).
- `ibp-kiosk-tool` for real against GitHub: first install, upgrade check,
  network down (installed version starts; never-installed tool gives the
  "Could not download" message), `--install-only` exit status, reinstall on a
  changed spec; installs of shippy, shippy-gui and ibp-printing[watcher];
  `ibp-label-watcher --help`, `ibp-print-diag --help`.
- `setup.d/50-apps.sh`'s uv install (download, checksum, skip when current,
  bad checksum warns without failing) and `60-shipping.sh`'s shippy-gui
  config logic (keep on rerun, replace with backup on a new secret), against
  scratch paths.
- `ibp-kiosk-log-upload`'s config parsing and checks, up to the mount.
- `systemd-analyze verify` on the units (no errors besides the scripts not
  being installed on the build machine).

Not verified (needs the VM or the hardware):

- Firefox: the policies and prefs under firefox-esr 153 (no restore page or
  safe-mode prompt after SIGTERM/SIGKILL; `--name` as the Wayland app_id;
  `--no-remote` with two profiles), the extension installing in both
  profiles, label printing from IBP Requests to `localhost:40121`, and the
  extension's background requests to `http://ibp-server.local` under ESR
  153's local network access checks.
- foot: the config is written from foot 1.21's documented keys but never
  loaded; full screen under labwc; font size on the laptops.
- shippy-gui (PyPI PySide6) under labwc: starts natively on Wayland with the
  libraries `60-shipping.sh` installs; dialogs.
- polkit: nmtui as `kiosk` can activate and edit connections.
- udev: the group rule and autosuspend on the real PM-2411-BT and DYMO;
  `power/control` actually stays `on`.
- The label watcher printing a label from `to-print` on the PM-2411-BT
  (expected to work; see above), and running as a user service from boot.
- Log upload against the real share (mount.cifs, rsync onto SMB, the
  `<hostname>` folder).
- The print server under the service user and `IPAddressDeny`; pycups
  building on trixie; the DYMO queue commands above.
- `setup.d` as a whole as root in the installer's chroot (runuser, uv
  tool installs there, `systemctl --global enable`).
