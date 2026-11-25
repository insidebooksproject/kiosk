"""One launcher per session, and the `home` command that talks to it.

The running launcher holds an exclusive flock on
$XDG_RUNTIME_DIR/ibp-kiosk/launcher.pid and writes its pid there.
`ibp-kiosk-launcher home` sends that pid SIGUSR1. If nobody holds the lock,
no launcher is running and `home` does nothing. This module does not import
Qt, so `home` starts fast.
"""

from __future__ import annotations

import fcntl
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

HOME_SIGNAL = signal.SIGUSR1
PID_FILE = "launcher.pid"


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / "ibp-kiosk"
    return Path(tempfile.gettempdir()) / f"ibp-kiosk-{os.getuid()}"


def pid_path() -> Path:
    return runtime_dir() / PID_FILE


class InstanceLock:
    """Held for the life of the launcher; the kernel drops it when we exit."""

    def __init__(self) -> None:
        self._fd: int | None = None

    def acquire(self, attempts: int = 5) -> bool:
        """True if we are the only launcher. Raises OSError on a setup problem."""
        directory = runtime_dir()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.stat().st_uid != os.getuid():
            raise OSError(f"{directory} belongs to another user")
        fd = os.open(directory / PID_FILE, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        for attempt in range(attempts):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                # A `home` command may hold it for a moment; retry briefly.
                if attempt == attempts - 1:
                    os.close(fd)
                    return False
                time.sleep(0.1)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd
        return True


def send_home() -> int:
    """Ask the running launcher to go home. Exit status for the CLI."""
    path = pid_path()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    except FileNotFoundError:
        return 0  # no launcher has run in this session
    except OSError as e:
        print(f"ibp-kiosk-launcher home: {path}: {e.strerror}", file=sys.stderr)
        return 1
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return 0  # nobody holds it: no launcher running
        except BlockingIOError:
            pass
        for _ in range(10):  # the launcher may not have written its pid yet
            text = os.pread(fd, 32, 0).decode(errors="replace").strip()
            if text.isdigit():
                break
            time.sleep(0.05)
        else:
            return 0
        try:
            os.kill(int(text), HOME_SIGNAL)
        except ProcessLookupError:
            pass
        except OSError as e:
            print(f"ibp-kiosk-launcher home: cannot signal {text}: {e.strerror}", file=sys.stderr)
            return 1
        return 0
    finally:
        os.close(fd)
