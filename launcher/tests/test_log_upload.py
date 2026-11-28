"""rootfs/usr/local/bin/ibp-kiosk-log-upload, run with stand-in commands.

Not the launcher, but the only test suite here: the script runs under dash
(the station's /bin/sh) with journalctl, systemctl, mount, mountpoint,
umount and rsync replaced by the stand-ins below, a folder as the share and
temporary state and runtime directories. Covers the journal export's day
budget and the copies; the VM test covers the real commands.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "rootfs/usr/local/bin/ibp-kiosk-log-upload"
SHELL = shutil.which("dash") or "sh"

# journalctl: -F lists the identifiers (one IBP one); -o json prints the
# entries of $FAKE_JOURNAL after the cursor in --cursor-file, at most -n of
# them, and saves the last one's cursor there, as journalctl does.
JOURNALCTL = r'''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if "-F" in args:
    if args[args.index("-F") + 1] == "SYSLOG_IDENTIFIER":
        print("ibp-kiosk")
    sys.exit(0)
n = int(args[args.index("-n") + 1])
cursor_file = next(a.split("=", 1)[1] for a in args if a.startswith("--cursor-file="))
lines = open(os.environ["FAKE_JOURNAL"]).read().splitlines(keepends=True)
cursors = [line.split('"__CURSOR":"', 1)[1].split('"', 1)[0] for line in lines]
start = 0
if os.path.exists(cursor_file):
    start = cursors.index(open(cursor_file).read().strip()) + 1
shown = lines[start:start + n]
sys.stdout.write("".join(shown))
if shown:
    with open(cursor_file, "w") as f:
        f.write(cursors[start + len(shown) - 1] + "\n")
'''

# rsync -rt ... SRC/ DEST/: a plain copy, failing for SRC in $FAIL_RSYNC.
RSYNC = r'''#!/bin/sh
for last; do :; done
src=
for arg; do [ "$arg" = "$last" ] || src=$arg; done
case " ${FAIL_RSYNC:-} " in
*" $src "*) echo "rsync: failed (stand-in)" >&2; exit 23 ;;
esac
mkdir -p "$last" && cp -R "$src." "$last"
'''

STUBS = {
    "journalctl": JOURNALCTL,
    "rsync": RSYNC,
    "systemctl": "#!/bin/sh\nexit 0\n",  # nothing failed
    "mount": "#!/bin/sh\nexit 0\n",  # the mount point is the share
    "mountpoint": "#!/bin/sh\nexit 1\n",
    "umount": "#!/bin/sh\nexit 0\n",
}


def entry(index: int, size: int) -> str:
    """Journal entry number ``index`` as journalctl's JSON line, ``size`` bytes."""
    head = {"__CURSOR": f"s=abc;i={index:x}", "PRIORITY": "3",
            "SYSLOG_IDENTIFIER": "ibp-kiosk"}
    line = json.dumps({**head, "MESSAGE": ""}, separators=(",", ":"))
    pad = size - len(line) - 1
    assert pad >= 0
    return json.dumps({**head, "MESSAGE": "x" * pad}, separators=(",", ":")) + "\n"


@dataclass
class Station:
    root: Path
    env: dict[str, str]

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def share(self) -> Path:
        return self.root / "run" / "share" / socket.gethostname()

    def day_file(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.state / "journal" / f"journal-{day}.jsonl"

    def journal(self, *entries: str) -> None:
        Path(self.env["FAKE_JOURNAL"]).write_text("".join(entries))

    def run(self, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([SHELL, str(SCRIPT)], env={**self.env, **env},
                              capture_output=True, text=True, timeout=60)

    def cursor(self) -> str:
        return (self.state / "cursor").read_text().strip()


@pytest.fixture
def station(tmp_path: Path) -> Station:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, text in STUBS.items():
        (bin_dir / name).write_text(text)
        (bin_dir / name).chmod(0o755)
    conf = tmp_path / "log-upload.conf"
    conf.write_text("SHARE=//server/share\nUSERNAME=station\nPASSWORD=secret\n")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "printer-shippy.log").write_text("printer log\n")
    print_logs = tmp_path / "print-logs"
    print_logs.mkdir()
    (print_logs / "printer-print-server.log").write_text("print server log\n")
    (tmp_path / "state").mkdir()
    env = {k: v for k, v in os.environ.items() if k != "JOURNAL_STREAM"}
    env.update({
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "IBP_KIOSK_LOG_UPLOAD_CONF": str(conf),
        "IBP_KIOSK_LOG_DIR": str(logs),
        "IBP_KIOSK_PRINT_LOG_DIR": str(print_logs),
        "IBP_KIOSK_LOG_UPLOAD_USER": "no-such-user-ibp-test",
        "RUNTIME_DIRECTORY": str(tmp_path / "run"),
        "STATE_DIRECTORY": str(tmp_path / "state"),
        "FAKE_JOURNAL": str(tmp_path / "journal.jsonl"),
    })
    return Station(tmp_path, env)


def test_the_day_budget_is_never_exceeded_and_nothing_is_skipped(station: Station) -> None:
    entries = [entry(i, 100) for i in range(1, 6)]
    station.journal(*entries)

    first = station.run(IBP_KIOSK_JOURNAL_MAX_DAY_BYTES="250")

    assert first.returncode == 0, first.stderr
    # Two whole entries fit in 250 bytes; the third waits.
    assert station.day_file().read_text() == "".join(entries[:2])
    assert station.cursor() == "s=abc;i=2"
    assert "the rest waits in the journal until tomorrow" in first.stderr

    again = station.run(IBP_KIOSK_JOURNAL_MAX_DAY_BYTES="250")

    assert again.returncode == 0, again.stderr
    assert station.day_file().read_text() == "".join(entries[:2])
    assert station.cursor() == "s=abc;i=2"

    # A bigger budget (a new day has the whole of it): the rest, once each.
    station.run(IBP_KIOSK_JOURNAL_MAX_DAY_BYTES="1000")

    assert station.day_file().read_text() == "".join(entries)
    assert station.cursor() == "s=abc;i=5"
    assert (station.share / "journal" / station.day_file().name).read_text() == "".join(entries)


def test_entries_over_the_run_limit_follow_in_later_runs(station: Station) -> None:
    entries = [entry(i, 100) for i in range(1, 6)]
    station.journal(*entries)

    for _ in range(3):
        result = station.run(IBP_KIOSK_JOURNAL_MAX_ENTRIES="2")
        assert result.returncode == 0, result.stderr

    assert station.day_file().read_text() == "".join(entries)
    assert station.cursor() == "s=abc;i=5"


def test_an_entry_bigger_than_a_whole_day_is_left_out(station: Station) -> None:
    """Else it would hold back every later entry for good."""
    station.journal(entry(1, 400), entry(2, 100))

    first = station.run(IBP_KIOSK_JOURNAL_MAX_DAY_BYTES="300")

    assert "left out an entry over 300 bytes" in first.stderr
    assert not station.day_file().exists() or station.day_file().read_text() == ""
    assert station.cursor() == "s=abc;i=1"

    station.run(IBP_KIOSK_JOURNAL_MAX_DAY_BYTES="300")

    assert station.day_file().read_text() == entry(2, 100)
    assert station.cursor() == "s=abc;i=2"


@pytest.mark.parametrize("failing", ["logs", "print-logs"])
def test_a_failed_copy_does_not_skip_the_others(station: Station, failing: str) -> None:
    station.journal(entry(1, 100))

    result = station.run(FAIL_RSYNC=f"{station.root / failing}/")

    assert result.returncode != 0
    assert "could not copy" in result.stderr
    assert (station.share / "journal" / station.day_file().name).read_text() == entry(1, 100)
    copied_logs = (station.share / "printer-shippy.log").exists()
    copied_print_logs = (station.share / "print-server" / "printer-print-server.log").exists()
    assert (copied_logs, copied_print_logs) == (failing != "logs", failing != "print-logs")


def test_a_failed_journal_copy_fails_the_run_after_the_logs(station: Station) -> None:
    station.journal(entry(1, 100))

    result = station.run(FAIL_RSYNC=f"{station.state / 'journal'}/")

    assert result.returncode != 0
    assert (station.share / "printer-shippy.log").read_text() == "printer log\n"
    assert not (station.share / "journal" / station.day_file().name).exists()


def test_everything_copied_exits_0(station: Station) -> None:
    station.journal(entry(1, 100))

    result = station.run()

    assert result.returncode == 0, result.stderr
    assert (station.share / "printer-shippy.log").exists()
    assert (station.share / "print-server" / "printer-print-server.log").exists()
    assert (station.share / "journal" / station.day_file().name).exists()
