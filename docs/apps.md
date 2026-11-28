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
| `rootfs/usr/local/bin/ibp-kiosk-log-upload` | Copies the label-printer and print-server logs and the journal export to the Samba share |
| `rootfs/usr/share/firefox-esr/distribution/policies.json` | Firefox policies (every browser tile) |
| `rootfs/etc/firefox-esr/ibp-kiosk.js` | Firefox prefs (every browser tile) |
| `rootfs/etc/gtk-3.0/settings.ini` | Firefox's window buttons: close only |
| `rootfs/usr/local/share/ibp-kiosk/firefox/ibp-kiosk-low-memory.js` | Low-memory prefs, copied to `/etc/firefox-esr/` on a machine with under 3 GiB of RAM |
| `rootfs/etc/ibp-kiosk/foot.ini` | The terminal's config |
| `rootfs/usr/local/bin/ibp-kiosk-bar`, `rootfs/etc/ibp-kiosk/waybar/` | The bar across the top of the screen |
| `rootfs/etc/ibp-kiosk/labwc/{rc.xml,themerc-override}`, `rootfs/usr/share/themes/IBP-Kiosk/` | The title bar on the terminal windows and Ship Manual |
| `rootfs/etc/uv/uv.toml` | uv: Debian's Python only, never download one |
| `rootfs/etc/polkit-1/rules.d/50-ibp-kiosk-network.rules` | Lets `kiosk` change network settings (Wi-Fi tile) |
| `rootfs/usr/local/share/ibp-kiosk/udev/*.rules` | Printer udev rules, copied to `/etc/udev/rules.d/` |
| `rootfs/etc/systemd/user/ibp-kiosk-label-watcher.service` | The label watcher, a `kiosk` user service |
| `rootfs/etc/systemd/system/ibp-kiosk-log-upload.{service,timer}` | Log upload every 15 minutes |
| `rootfs/etc/systemd/system/ibp-kiosk-print-server{,-update}.service` | ibp-print-server and its update from GitHub |
| `setup.d/50-apps.sh` | Low-memory prefs (under 3 GiB of RAM); git and uv |
| `setup.d/60-shipping.sh` | The shipping config, the PM-2411-BT, the label watcher, log upload |
| `setup.d/70-package-printer.sh` | The DYMO and ibp-print-server |
| `packages/apps.txt` | Debian packages every station gets |

## Tiles

| `ibp-kiosk-app` | Runs |
|---|---|
| `portal` | `firefox-esr --no-remote --profile ~/.local/share/ibp-kiosk/firefox/portal --name ibp-kiosk-portal https://bookportal.tdcj.texas.gov/BookPortal/protected/dashboard.action` |
| `requests` | the same with profile `requests`, app_id `ibp-kiosk-requests`, on `http://192.168.1.156/` |
| `packages` | the same as `requests` (same profile and app_id), on `http://192.168.1.156/packages` |
| `ship-individual`, `ship-bulk` | foot, maximized, with a title bar, running `shippy --config /home/kiosk/.config/shippy/config.ini individual` / `bulk` (below) |
| `ship-manual` | `shippy-gui -qwindowtitle "Ship Manual"` (Qt's option; the title bar shows it), from `/home/kiosk/.config/shippy` (it reads `config.ini` from its working directory) |
| `wifi` | the same terminal running `nmtui` |
| `print-diag` | the same terminal running `ibp-print-diag`, then "press any key" |

`ibp-kiosk-app` stays in the foreground (it `exec`s the app, so the launcher's
SIGTERM to the process group reaches the app itself) and exits with the
app's status. When something is missing it prints one line on stderr and
exits 1 (2 for a bad argument), e.g. "Shipping is not set up on this machine:
/home/kiosk/.config/shippy/config.ini is missing or not readable. Ask an IBP
admin." (Ship Manual's says "Ship Manual is not set up on this machine: ...").
It checks, before starting anything: the shipping config (the three ship
tiles), `firefox-esr`, `foot`, `nmtui` and `/usr/local/bin/uv`.

The start pages can be changed without editing the script: an optional
`/etc/ibp-kiosk/apps.conf` (shell syntax, not installed by default) may set
`PORTAL_URL`, `REQUESTS_URL`, `PACKAGES_URL` (default: `/packages` under
`REQUESTS_URL`) and, for `ibp-kiosk-status server`,
`IBP_SERVER_URL` (default `http://192.168.1.156`).

### Browser tiles

- **An ordinary window** (since 2026-11-25), not `--kiosk`: tabs, address
  bar, and volunteers can open other pages. labwc gives main windows no
  title bar, so Firefox draws its own buttons in the tab bar
  (`browser.tabs.inTitlebar`), and `/etc/gtk-3.0/settings.ini` leaves only
  the close button; closing the window ends Firefox and the launcher shows
  the tiles.
- **URLs.** The portal's is the predecessor's start page
  (`ibp-book-portal-kiosk`'s `policies.json`), which sends a signed-out
  volunteer to the login (ID.me). The IBP frontend's is the "App" address in
  `ops/ibp-server.md` (the meta repo): `http://192.168.1.156/`, LAN and tailnet
  only, the same server address `shippy`'s `sample.ini` uses. On the IBP
  tailnet (since 2026-11-26) the server is `http://ibp-server/` or
  `http://100.92.207.121/`; the defaults still use the LAN address. The Pi's LAN
  address is static. (`http://ibp-server.local/` also works where mDNS does;
  the extension uses that name.)
- **One `policies.json` for all.** Firefox reads policies system-wide, so
  every tile gets the predecessor's lockdown (no about:config, dev tools,
  other add-ons, `file://` pages or saved passwords; DoH off so
  `ibp-server.local` resolves; Firefox's own updater off, as Debian's
  package updates it)
  and the force-installed IBP Book Portal Scanner extension. The predecessor's
  locked `Homepage` policy is gone: each tile's start page is passed on the
  command line and written to its profile's `user.js` (for Alt+Home).
  Added: `DisableProfileRefresh` and `DisableSafeMode`, so repeated unclean
  exits never offer a refresh or safe mode.
- **Nothing is kept between volunteers** (since 2026-11-26). The policy
  `SanitizeOnShutdown` clears cookies, site storage, history, the cache,
  form entries and site permissions each time Firefox closes, so the next
  volunteer never inherits a sign-in: the Book Portal asks for ID.me every
  time the tile is opened. The Home key and a power cut end Firefox without
  a clean close; it would then clear at its next start, but only after
  asking for the start page with the old cookies (seen in the VM, 3 runs of
  3). So `ibp-kiosk-app` removes the cookies, site storage, history, open
  tabs and cache from the profile before every start, and Firefox clears
  the rest. Extension storage is not site storage and both leave it alone,
  so the extension's server setting and its queue of unsent registration
  reports survive. Files a volunteer downloaded stay in
  `/home/kiosk/Downloads`; no tile can open them (`file://` is blocked).
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
- **Low memory** (a machine with under 3 GiB of RAM: the 2 GB Chromebook): one content
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
| `shippy` (or `shippy-gui`, the same tool) | `shippy[gui] @ git+https://github.com/insidebooksproject/shippy.git@deploy` | Ship Individual, Ship Bulk, Ship Manual |
| `ibp-printing` | `ibp-printing[watcher] @ git+https://github.com/insidebooksproject/printing.git@deploy` | label watcher, Printer check (`--no-upgrade`) |
| `ibp-printing-server` | `ibp-printing @ ...@deploy` | the print server (user `ibp-kiosk-print`) |

Releasing an app stays as it is: fast-forward its repo's `deploy`; stations
pick it up at the next launch (the watcher and print server at their next
start, i.e. boot). A changed SPEC in this script (recorded in
`~/.local/state/ibp-kiosk/tools/TOOL.spec`) reinstalls the tool. A lock
(`flock`) keeps two installs of one tool apart. `setup.d` preinstalls every
tool (as the user that runs it), so the first launch is quick
and works offline; if that fails at install time, the first launch installs
it instead (the gui extra's PySide6 is about 700 MB, so that takes minutes with
no window showing).

**uv's offline mode, as observed** (uv 0.12.9 on this build machine,
2026-11-24; network "down" simulated with an unreachable `https_proxy`):

| Command | Result |
|---|---|
| `uvx --from git+https://github.com/insidebooksproject/shippy.git@deploy shippy --help`, cold cache | works, 3.4 s |
| same, warm cache | works, 0.7 s (still fetches the branch) |
| same with `--offline`, warm cache, network up | fails at once: "failed to fetch branch or tag `deploy`: Remote Git fetches are not allowed because network connectivity is disabled (i.e., with `--offline`)" |
| `uvx --offline --from git+...shippy.git@<commit sha>`, warm cache for that sha | fails the same way, on shippy's own dependency `ibp-printing @ git+...@v0.4.0`: uv must fetch a tag too |
| any of these online with the network down | fails after 4 to 8 s (uv's retries) |
| `uv tool install git+...shippy.git@deploy`, then network down: `uv tool upgrade shippy` | fails after about 7 s; the installed `~/.local/bin/shippy` still runs |
| `uv tool upgrade` after a new commit on the branch (local test repo) | installs the new commit |

So `uvx --offline` cannot start anything from a git branch or tag, cached or
not; the first design's "retry with uv's offline mode" would never work. A tool
install, upgraded at launch, is the offline fallback.

**uv itself.** Debian 13 has no `uv` package (it is only in unstable, as of
2026-11-24). `50-apps.sh` installs Astral's static build
(`uv-x86_64-unknown-linux-gnu.tar.gz`, pinned version and SHA-256 in the
script) to `/usr/local/bin/uv` and `uvx`, plus Debian's `git` (uv fetches
git sources with it). To update uv, bump `IBP_APPS_UV_VERSION` and the two
checksums (from the release's `.sha256` files) and rerun `setup.sh`; `uv
self update` is not used.
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

### The shipping config

Ship Individual, Ship Bulk and Ship Manual share one file (since
2026-11-28, when shippy-gui became part of the `shippy` package; the
Windows laptops share `C:\Users\insid\config.ini` the same way):
`/home/kiosk/.config/shippy/config.ini`, kiosk:kiosk 0600 in a 0700
directory. shippy gets it with `--config`; shippy-gui runs in that
directory, reads `config.ini` there, writes it from its Settings dialog and
keeps its own log, `shippy.log`, next to it, so the directory belongs to
`kiosk`. `ibp-kiosk-app` (`$HOME/.config/shippy`) and `60-shipping.sh`
each name the path.

What it must hold (the template is `config.example.ini` in the shippy
repo): `[ibp]` `url`, `[easypost]` `apikey` and `[googlemaps]` `apikey`.
shippy needs the three sections; shippy-gui also refuses a blank EasyPost or
Google Maps key (it shows "Config file is invalid or incomplete" and opens
Settings). `[ui]` (font size, default weight, log file) is shippy-gui's
only, optional, and ignored by shippy; `[parcel]` is optional and read by
both. So a file written for shippy alone works for all three tiles as long
as those two keys aren't blank. Saving from Settings rewrites the file: it
keeps the other sections (`[parcel]`), writes `[ui]` and drops comments.

The secret is `shippy.ini` (`build.sh`'s `KIOSK_SHIPPY_CONFIG`). Volunteers
change the file from Settings, so `60-shipping.sh` replaces it only with a
secret it doesn't already hold: `/var/lib/ibp-kiosk/shippy.ini.sha256`
lists the checksums of the secrets it came from, one per line, and the
replaced file is kept as `config.ini.bak-<date>`. To install the same
secret again anyway, delete the checksum file first. An old secrets directory's
`shippy-gui.ini` is used only when there is no `shippy.ini` (with a
warning), and ignored with a warning when there is one.

**Stations set up before 2026-11-28** had two: shippy's
`/etc/ibp-kiosk/shippy.ini` (root:kiosk 0640) and shippy-gui's
`/home/kiosk/.config/shippy-gui/config.ini` (with its secret's checksum in
`/var/lib/ibp-kiosk/shippy-gui.ini.sha256`). When the new file is missing,
`60-shipping.sh` (at the boot update, with no secrets) creates it from
shippy-gui's, which has the volunteer's saved settings and keys both apps
need, else from shippy's. Its stamp gets the checksums of both old secrets,
so a rerun with the old stick keeps the copy. The old files are left in
place, unread: a rollback of `deploy` would still use them, and either may
hold a key the other lacks. Delete them by hand once all three tiles work.

### Ship Individual, Ship Bulk (foot)

`foot --log-level=error --config=/etc/ibp-kiosk/foot.ini
--app-id=ibp-kiosk-ship-individual --title="Ship Individual" --maximized --
ibp-kiosk-app --in-terminal ship-individual`. labwc gives the
window a title bar with the tile's name ("Ship Individual", "Ship Bulk"), so
the screen always says which mode is open, and a close button that returns
to the tiles (window rules in `rc.xml`; colours and the button size in
`themerc-override`; the button's picture in
`/usr/share/themes/IBP-Kiosk/labwc`). Inside, shippy
runs through `ibp-kiosk-tool` (so the update check is visible on screen). The
terminal closes when shippy exits 0 or 130 (130 is the volunteer quitting:
shippy's "Press Ctrl+C to quit" at the no-printer prompt since shippy
cdfc8f7, or an unhandled Ctrl+C). After any other non-zero exit the screen says
"shippy stopped (exit status N). Read the message above, then press any key
to close." Keys typed before that message (a scanner's Enter) are discarded
first, and the status goes to the journal (`ibp-kiosk-app`). Either way the
launcher then shows the tiles, not its failure screen: the volunteer has
already read the error where it was printed. foot's own warnings are off
(`--log-level=error`), so they never show up as the reason an app stopped.
The Home key or the close button (a hangup, also a normal exit) closes it
at any time.

`foot.ini`: DejaVu Sans Mono 16 pt (about 150 x 45 on a 1920x1080 screen),
10000 lines of scrollback, and no key that starts another program (no new
terminal window, no URL launcher).

### Ship Manual (shippy-gui)

Runs from `/home/kiosk/.config/shippy` with `QT_QPA_PLATFORM=wayland;xcb`,
on the shared config (above), which its Settings dialog writes.

**No CUPS.** ibp-printing dropped CUPS on 2026-11-26: on Linux it prints
only to the printers it drives directly over USB (usblp), the PM-2411-BT
here, and its `linux` extra is empty. So the shipping stations need no CUPS
packages at all.

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
without an upgrade, then "Done (exit status N). Press any key to close."

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
| `printers` | both checks above; the strip's one printer chip. A problem when either check fails with anything but "Not plugged in", or when neither printer is ready | "Shipping printer ready (BOB)", "Package printer ready", "Shipping printer ready (BOB), package printer ready", "Shipping printer: Plugged in, but not allowed (udev rule missing?)", "Package printer: Print server not running", "Not plugged in" |
| `update` | the first word and the text of `/var/lib/ibp-kiosk/update/status`, written by `ibp-kiosk-update` (each run first writes "Checking…", so no text is left over from the last boot); a problem only for `failed` | "Not checked yet", "Checking…", "Up to date", "Updating…", "Updated (restart to finish)", "Could not check (no internet?)", "Off on this machine", "Update failed (tell an IBP admin)" |
| `battery` | sysfs only: the first `/sys/class/power_supply/*` of type `Battery` that is present and isn't a mouse's or keyboard's (`scope` `Device`). The charge is `capacity`; the time left is `charge_now` over `current_avg` (or `current_now`), or `energy_now` over `power_now`, shown when it is 12 hours or less. A problem on battery at 20% or less, or with under 15 minutes left | "Plugged in (86%)", "Charging (40%)", "86%, about 2½ hours left", "25%, about 40 minutes left", "86%, not plugged in" (no estimate yet), "15%, plug in the charger", "Can't be read"; nothing at all with no battery |

`battery` is not on the launcher's strip: the bar shows it
(`ibp-kiosk-bar battery`, every 15 s, "Battery: " and the text, red when the
check reports a problem), so it is in view while an app is open.

`printer-shipping` never opens the device: usblp allows one open, and
shippy or the watcher may be printing. Reading `ieee1284_id` returns the ID
usblp cached when the printer was plugged in.

## Shipping printer (PM-2411-BT)

`/etc/udev/rules.d/60-ibp-kiosk-label-printer.rules` (`60-shipping.sh`):

- `/dev/usb/lpN` of USB vendor `2e3c` gets group `kiosk`, mode 0660. The
  upstream rule (the printing repo's `packaging/linux/60-ibp-label-printer.rules`)
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
  (`DirectFirstBackend`: the PM-2411-BT over usblp; Linux has no queues),
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
SHARE=//192.168.1.156/ibp-logs-<station>
USERNAME=ibplogs-<station>
PASSWORD=...
```

`192.168.1.156` is ibp-server's LAN address. Its old personal-tailnet
address `100.119.68.125` (named in older examples, including the comment in
`ibp-kiosk-log-upload`) is gone since ibp-server moved to the IBP tailnet on
2026-11-26; there it is `ibp-server` (`100.92.207.121`), which
`tag:ibp-station` reaches on tcp 445. Pointing stations at it is in the
workspace's `BACKLOG.md`.

The script reads the file (never sources it; one pair of quotes around a
value is removed), writes a mount.cifs credentials file in the service's
root-only runtime directory, mounts the share in the service's private mount
namespace (`PrivateMounts=yes`, so it never outlives the service), deletes
the credentials file, and runs `rsync -rt --modify-window=2` (no `--delete`)
from `/home/kiosk/.local/state/ibp-printing/logs/` to `<share>/<hostname>/`,
and the print server's log directory
(`/var/lib/ibp-kiosk-print/.local/state/ibp-printing/logs/`, since
2026-11-28) to `<share>/<hostname>/print-server/` (its own folder: both
directories can hold a `printer.log`). Either is skipped when it doesn't
exist. The password is never on a command line. The host-named folder keeps a
station that reuses an old laptop's share from overwriting that laptop's
Windows logs (same file names). Each station still needs its own share and
account on ibp-server (`ops/ibp-server.md`, "Samba shares").

### Journal export

Before it mounts the share, the script exports what the station's journal
has to say about IBP into its state directory
(`/var/lib/ibp-kiosk-log-upload/`, root 0700), and the rsync above then
copies `journal/` there to `<share>/<hostname>/journal/` (also without
`--delete`). It is the kiosk's part of the workspace's error reporting
(`docs/error-reporting.md` in the IBP workspace): the launcher, labwc, the
tile scripts and the IBP units write to the journal, not to files, so the
weekly digest on ibp-server reads them from there. Two kinds of file, both
JSONL, one per UTC day:

- `journal-<YYYY-MM-DD>.jsonl`: journal entries at warning or above
  (`journalctl -p warning -o json`) since the last run, as journald writes
  them, field names unchanged (`__REALTIME_TIMESTAMP`, `MESSAGE`,
  `PRIORITY`, `SYSLOG_IDENTIFIER`, `_SYSTEMD_UNIT`, ...). Only these fields
  are kept: `MESSAGE PRIORITY SYSLOG_IDENTIFIER _SYSTEMD_UNIT
  _SYSTEMD_USER_UNIT UNIT USER_UNIT _HOSTNAME _PID _COMM _TRANSPORT
  MESSAGE_ID ERRNO EXIT_CODE EXIT_STATUS JOB_RESULT CODE_FILE CODE_LINE
  CODE_FUNC`, plus the ones journalctl always adds (`__CURSOR`,
  `__MONOTONIC_TIMESTAMP`, `__SEQNUM`, `__SEQNUM_ID`, `_BOOT_ID`); a field
  over 4096 bytes is `null`. An entry is IBP's when one of
  `SYSLOG_IDENTIFIER`, `_SYSTEMD_UNIT`, `_SYSTEMD_USER_UNIT`, `UNIT` or
  `USER_UNIT` starts with `ibp-`: the session (`ibp-kiosk`: labwc, the
  launcher and what the tiles print), `ibp-kiosk-app`, every `ibp-kiosk-*`
  system unit, the label watcher (a user unit), and systemd's own messages
  about those units (a failed run, a restart). `journalctl -F` finds the
  values, so a new `ibp-` unit is included without a change here.
- `failed-units-<YYYY-MM-DD>.jsonl`: the units failed now (`systemctl
  --failed`, the system's and the `kiosk` user manager's when it runs),
  rewritten whole at every run, so the day's file is that day's last list
  and a unit that stays failed is in the file of every day the station
  runs. Each line is shaped like a journal entry: `__REALTIME_TIMESTAMP`
  (microseconds, one value for the whole list, the run's time),
  `_HOSTNAME`, `SYSLOG_IDENTIFIER` `ibp-kiosk-log-upload`, `PRIORITY` `3`,
  `MESSAGE` `<unit> failed`, and `UNIT` (system) or `USER_UNIT` (kiosk's)
  with the unit's name. Nothing failed is an empty file: emptied rather
  than removed, since the share (no `--delete`) would keep a list written
  earlier that day. When a list can't be read, the file stays as it was.

The journal's place is kept by `journalctl --cursor-file`
(`/var/lib/ibp-kiosk-log-upload/cursor`), saved only once the entries are
in the day's file, so a run that fails part-way exports them again. Both
files are written whole and renamed into place (the day's journal file is
copied, the new entries added to the copy, and the copy renamed over it;
the temporary files are in the state directory, outside `journal/`), so a
run killed part-way (a shutdown, the unit's timeout) never leaves a cut-off
line. A run killed after the rename and before the cursor is saved exports
the same entries again at the next run: whole lines, with the same
`__CURSOR`, which the digest can dedupe on. That is the trade made: a rare
duplicate rather than a lost entry.

What it doesn't break:

- **The export fails** (journalctl or systemctl errors, a full disk): a
  warning in the journal (`<4>`, so the next export carries it), and the
  label-printer logs are copied as before. A cursor journalctl refuses is
  deleted, and the next run starts again from the newest entries (some
  entries may then be exported twice).
- **No network, or the share can't be reached:** the files stay in
  `/var/lib/ibp-kiosk-log-upload/journal/` and go at the next run that
  mounts the share; the unit fails as before.
- **One copy fails** (the label-printer logs, the print server's or the
  journal export): the others are still tried, and the unit fails.
- **No label-printer logs yet:** the journal export is still copied (until
  now the run stopped there).

Limits on what one run writes: at most 500 entries (`-n 500` after the
cursor; the next runs take the rest, so nothing is skipped), each field at
most 4096 bytes, and at most 4 MiB of journal entries a day, counted in
whole entries: a run writes only the entries that still fit, the cursor
moves past those only, and the rest waits in the journal for the next day
(journald's own size limits apply). An entry bigger than a whole day's
budget, which can't happen with fields capped at 4096 bytes, is left out
with a warning rather than holding back every later one. The spooled files
are deleted after 30 days, copied or not. The unit's `TimeoutStartSec` went
from 10 to 20 minutes for the extra steps (each has its own `timeout`).
`launcher/tests/test_log_upload.py` runs the script under dash with
stand-ins for journalctl, systemctl, mount and rsync (the day budget, the
run limit, the copies).

What the export finds depends on the priority an entry is logged at. A
service's or `systemd-cat`'s output is logged at info unless a line starts
with a syslog prefix such as `<3>`: the launcher adds one to its own log
lines when its stderr is the journal (`JOURNAL_STREAM`), `ibp-kiosk-app`
logs an app that stopped with an error at `err`, and so does
`ibp-kiosk-update` a failed update. What the tiles' apps print goes to the
journal at info and is not exported; their errors reach the share through
their own `errors-<app>.jsonl` (ibp-printing), which is in the log
directory above.

Run it now: `sudo systemctl start ibp-kiosk-log-upload`; result:
`journalctl -u ibp-kiosk-log-upload -n 20`; what it exported:
`sudo ls -l /var/lib/ibp-kiosk-log-upload/journal/`.

## Package printer (DYMO) and ibp-print-server

`70-package-printer.sh`, on every station:

- Installs `cups cups-client cups-filters`, only so that Firefox can print
  the frontend's label PDF (the fallback when the print server fails). No
  DYMO driver and no DYMO queue: the print server drives the printer
  directly over USB (the printing repo's `docs/printers/dymo-lw450.md`).
- Creates the system user `ibp-kiosk-print` (home `/var/lib/ibp-kiosk-print`)
  and preinstalls `ibp-printing` from `deploy` as that user.
- Enables `cups` and `ibp-kiosk-print-server.service`, which runs
  `ibp-print-server server` (port 40121) as `ibp-kiosk-print`, with
  `SupplementaryGroups=lp` so it can open `/dev/usb/lpN`. Its `Wants=`
  starts `ibp-kiosk-print-server-update.service` first (`uv tool upgrade`,
  as upstream's `ExecStartPre`), so every boot picks up `deploy`; if that
  fails the installed version starts. The server unit allows only loopback
  traffic (`IPAddressDeny=any`, `IPAddressAllow=localhost`): the server
  listens on every interface, but only this machine's browser needs it.
  That is why the update is a separate unit.
- Why a service user and not `kiosk` or the admin: the Home key can't touch
  it, it has its own tool install, and an admin account isn't needed (upstream runs it as `ibp`, the intake station's
  login).
- USB autosuspend off for DYMO devices (vendor `0922`).
- No resume unit: the stations shut down on lid close.

**On site:** plug in the DYMO (loaded with 30321 labels, the size the
printing repo's model assumes). Nothing to set up. Then check, without and
with a print:

```sh
curl -s localhost:40121/health        # "count": 1
ibp-kiosk-status printer-package      # Ready
sudo -u ibp-kiosk-print -g lp -H /var/lib/ibp-kiosk-print/.local/bin/ibp-print-server list
sudo -u ibp-kiosk-print -g lp -H /var/lib/ibp-kiosk-print/.local/bin/ibp-print-server test   # prints a test label
```

## Where things are on a station

| What | Where |
|---|---|
| Shipping config (all three ship tiles) | `/home/kiosk/.config/shippy/config.ini` (kiosk 0600); Ship Manual's log `shippy.log` next to it. Stations from before 2026-11-28 also keep the unread `/etc/ibp-kiosk/shippy.ini` and `/home/kiosk/.config/shippy-gui/` |
| Log upload config | `/etc/ibp-kiosk/log-upload.conf` (root 0600) |
| Optional URL overrides | `/etc/ibp-kiosk/apps.conf` |
| Firefox profiles | `/home/kiosk/.local/share/ibp-kiosk/firefox/{portal,requests}` (IBP Packages uses `requests`) |
| Installed apps (uv tools) | `/home/kiosk/.local/share/uv/tools`, commands in `/home/kiosk/.local/bin`, cache `/home/kiosk/.cache/uv`; print server: the same under `/var/lib/ibp-kiosk-print` |
| shippy, shippy-gui, watcher, diag logs | `/home/kiosk/.local/state/ibp-printing/logs/printer-{shippy,shippy-gui,watcher,diag}.{log,jsonl}` |
| Label journal, watcher state | `/home/kiosk/.local/state/ibp-printing/` |
| Labels waiting to print | `/home/kiosk/Downloads/to-print/` (`printed/`, `check-printer/` next to it) |
| Watcher journal | `sudo journalctl _SYSTEMD_USER_UNIT=ibp-kiosk-label-watcher.service` |
| Print server | `journalctl -u ibp-kiosk-print-server`; `/var/lib/ibp-kiosk-print/.local/state/ibp-printing/logs/printer-print-server.log` (copied to the share's `<hostname>/print-server/`) |
| Log upload | `journalctl -u ibp-kiosk-log-upload`; journal export and its cursor in `/var/lib/ibp-kiosk-log-upload/` (root 0700) |

## Tested and not verified

Tested on the build machine (Pop!_OS, uv 0.12.9) on 2026-11-24 (the VM run
is in `CLAUDE.md`, "State"):

- `shellcheck` and `sh -n` (dash) on every script and `setup.d` step.
- `ibp-kiosk-status network` (real NetworkManager, Wi-Fi), `server` (real:
  not reachable after 3 s, off the IBP LAN; against a local fake
  `/api/health`: OK, 404, unreachable),
  `printer-package` against a fake `/health` (ready, count 0, degraded, not
  running), `printer-shipping` against a fake sysfs tree (no printer, DYMO
  only, PM2411BT without node, without access, ready as BOB and BETTY,
  model by 1284 `MODEL:` in lower case, plugged in but not bound to usblp).
- `ibp-kiosk-status printers` (2026-11-26) against the same fakes: neither
  printer, either one, both, and a problem with each while the other is
  ready.
- `ibp-kiosk-status battery` (2026-11-26) against fake sysfs trees (no
  battery, mains only, a mouse's battery, not present, full, charging, on
  battery by charge and by energy, a negative current, no current reading
  yet, 20%, a few minutes left, an unreadable value) and on `ibp-bilbo` on
  mains power ("Plugged in (86%)"). Not seen on battery on real hardware.
- The bar in the VM (2026-11-26, waybar 0.12.0, about 45 MB of memory): see
  `CLAUDE.md`, "State".
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
  bad checksum warns without failing) and `60-shipping.sh`'s config logic,
  against scratch paths (2026-11-28, the shared config): a fresh install;
  a rerun without secrets and with the same secret keeps saved settings; a
  new secret replaces the file and keeps a backup; migration from the two
  old configs (from shippy-gui's, or shippy's alone) at a rerun without
  secrets, then reruns with the old stick's secrets keep the copy; an old
  `shippy-gui.ini` alone; no config at all.
- `ibp-kiosk-log-upload`'s config parsing and checks, up to the mount.
- `ibp-kiosk-log-upload`'s journal export (2026-11-28, systemd 255, dash,
  against the build machine's real journal, with a stand-in `mount` and a
  local folder as the share, not as root): the first run takes the newest
  500, later runs only what is new (info entries and other identifiers
  left out); with `-n 2`, five new entries over three runs, none twice or
  missed; the day cap; the share unreachable (the files wait, the next run
  copies them); a garbage cursor (deleted, warning at priority 4 under
  `systemd-cat`, logs still copied); journalctl failing (logs still
  copied); no label-printer log directory (journal still copied). The
  failed-units list with a stand-in `systemctl` and `setpriv`: nothing
  failed (an empty file), system and user units (one of them with `\x2d`
  and quotes, valid JSON), the same list at the next run (rewritten with
  the new time, and copied to the share), a user listing that fails (the
  file unchanged, a warning), and cleared (emptied, also on the share).
  Crash safety (2026-11-28): a failed rename of the day's file (the file
  and cursor unchanged, the entries exported once at the next run); a lost
  cursor save after the rename (the entries twice, whole lines); 40 runs
  killed with SIGKILL at random moments while 1,600 entries came in, then
  drained (every line valid JSON, none missing).
- `systemd-analyze verify` on the units (no errors besides the scripts not
  being installed on the build machine).

Not verified (needs the VM or the hardware):

- Firefox: the close button it draws in its tab bar under labwc; the
  policies and prefs under firefox-esr 153 (no restore page or
  safe-mode prompt after SIGTERM/SIGKILL; `--name` as the Wayland app_id;
  `--no-remote` with two profiles), the extension installing in both
  profiles, label printing from IBP Requests to `localhost:40121`, and the
  extension's background requests to `http://ibp-server.local` under ESR
  153's local network access checks.
- foot: font size on the laptops.
- shippy-gui (PyPI PySide6): whether it runs natively on Wayland or falls
  back to XWayland (the VM showed it maximized, with its Settings dialog as
  a dialog), and font scaling on the laptops.
- polkit: nmtui as `kiosk` can activate and edit connections.
- udev: the group rule and autosuspend on the real PM-2411-BT and DYMO;
  `power/control` actually stays `on`.
- The label watcher printing a label from `to-print` on the PM-2411-BT
  (expected to work; see above).
- Log upload against the real share (mount.cifs, rsync onto SMB, the
  `<hostname>` folder).
- The journal export on real hardware and against the real share (tested
  in the VM 2026-11-28, as root under the unit, on systemd 257, against a
  local Samba share: `CLAUDE.md`, "State").
- The print server under the service user, `IPAddressDeny` and
  `SupplementaryGroups=lp` (the same server prints directly on the intake
  station since 2026-11-26).
- The uv tool preinstalls in the installer's chroot (the VM install ran
  `setup.d` there; whether the preinstalls worked or the first launches
  installed the tools is not recorded).
