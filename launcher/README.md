# ibp_kiosk: the station launcher

A full-screen PySide6 window with one tile per task, a status strip, and
Shut down / Restart buttons. It reads `/etc/ibp-kiosk/station.toml` (schema in
`../CLAUDE.md`) and runs each tile's `command` as a child process, one at a
time. On a station it is copied to `/usr/local/lib/ibp-kiosk/ibp_kiosk/` and
run by `ibp-kiosk-launcher` with Debian's `python3` and PySide6
(`../packages/launcher.txt`).

## Run it on a development machine

Needs [uv](https://docs.astral.sh/uv/). `pyproject.toml` is for development
only; it pins PySide6 to Debian 13's version.

```sh
cd launcher
IBP_KIOSK_POWEROFF=true IBP_KIOSK_REBOOT=true \
  uv run python -m ibp_kiosk --config examples/station.toml --windowed
```

`--windowed` opens a closable 1366x768 window instead of a full-screen one
that ignores close requests. The `IBP_KIOSK_POWEROFF` / `IBP_KIOSK_REBOOT`
variables replace `systemctl poweroff` / `systemctl reboot` (split like a shell
command line, no shell), so the power buttons don't turn your machine off.
From another terminal:

```sh
uv run python -m ibp_kiosk home   # close the running app, show the tiles
```

Options: `--config PATH` (or `IBP_KIOSK_CONFIG`; default
`/etc/ibp-kiosk/station.toml`).

## Keys

| Key | Does |
|---|---|
| Arrow keys, Tab | Move between tiles and buttons |
| Enter, Space, click | Press the tile or button |
| 1 to 9 | Start the tile with that number |
| Ctrl+Alt+A | Admin screen (not while an app runs): hostname, IP addresses, version, `[[admin]]` tiles |
| Esc | Leave the admin, failure or confirm screen |
| `ibp-kiosk-launcher home` | Bound to Super by labwc: close the app, show the tiles |

## How it behaves

- **Apps.** A tile's command runs in its own session and process group, with
  stdout and stderr merged into one pipe that is always drained. Each line is
  copied to the launcher's stderr as `[tile-id] line` (so it reaches the
  journal) and the last 15 are kept. If the app exits non-zero, or within 3
  seconds, the failure screen shows them, unless the launcher stopped it.
  When the app exits, the rest of its process group gets SIGTERM. While it
  runs, the launcher's own page (behind the app) says so and has a Close
  button.
- **Home.** The launcher holds an exclusive `flock` on
  `$XDG_RUNTIME_DIR/ibp-kiosk/launcher.pid` and writes its pid there. `home`
  sends that pid SIGUSR1; if the file is missing or unlocked, no launcher is
  running and it exits 0 without output. The launcher then sends SIGTERM to
  the app's process group and SIGKILL 5 seconds later if anything is left.
  The same lock keeps a second launcher from starting (it logs and exits 0).
- **Status strip.** Each `[[status]]` command runs in a worker thread every
  `interval` seconds, with a 10 second timeout. Exit 0 shows a check mark,
  anything else (including a timeout or a missing program) a cross on a red
  chip. A chip shows the mark and the check's label, and the chips share the
  width equally; the first line of stdout is the chip's tooltip (hover, or
  click the chip). With `show_text = true` the chip shows that line after
  the label too and counts as two chips in width; it is hidden until its
  first result, and whenever the check exits 0 and prints nothing. Changes
  are logged.
- **Errors.** A missing or invalid `station.toml` shows a full-screen message
  with the reason and the power buttons. Unexpected exceptions are logged to
  stderr and never end the launcher. SIGTERM, SIGINT or SIGHUP stop the
  running app, then the launcher.
- The Wayland app_id is `ibp-kiosk-launcher` (for labwc window rules).

## Tests

```sh
cd launcher
uv run pytest
```

They run Qt with `QT_QPA_PLATFORM=offscreen` (set in `tests/conftest.py`)
and start real child processes (`sh`, `sleep`, `true`, `false`), so they need
a Unix machine but no display. `tests/test_home.py` starts the whole launcher
as a subprocess and drives it with `home`.
