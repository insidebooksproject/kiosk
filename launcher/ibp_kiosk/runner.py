"""Run one app at a time as a child in its own process group.

The child's stdout and stderr go to one pipe. A reader thread drains it
(so a chatty child never blocks on a full pipe), copies each line to the
launcher's stderr for the journal, and keeps the last lines for the failure
screen. A waiter thread waits for the child and reports back through the
finished signal, which Qt delivers on the UI thread.
"""

from __future__ import annotations

import collections
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import IO

from PySide6.QtCore import QObject, QTimer, Signal

from .config import Tile

log = logging.getLogger(__name__)

TAIL_LINES = 15
QUICK_EXIT_SECONDS = 3.0
KILL_AFTER_SECONDS = 5.0
# How long to wait for the output pipe to close after the child exits
# (helpers it started may still hold it open).
DRAIN_SECONDS = 2.0


@dataclass(frozen=True)
class RunResult:
    tile: Tile
    returncode: int | None  # None if it never started
    seconds: float
    tail: tuple[str, ...]
    stopped: bool  # we stopped it (Home key or launcher exit)
    error: str = ""  # why it could not be started
    quick_exit_seconds: float = QUICK_EXIT_SECONDS

    @property
    def failed(self) -> bool:
        if self.stopped:
            return False
        return bool(self.error) or self.returncode != 0 or self.seconds < self.quick_exit_seconds

    @property
    def quick(self) -> bool:
        return self.returncode is None or self.seconds < self.quick_exit_seconds


class _Run:
    """State of one child. Fields set by the threads are guarded by lock."""

    def __init__(self, tile: Tile, proc: subprocess.Popen[bytes]) -> None:
        self.tile = tile
        self.proc = proc
        self.started = time.monotonic()
        self.tail: collections.deque[str] = collections.deque(maxlen=TAIL_LINES)
        self.lock = threading.Lock()
        self.reaped = False
        self.stopping = False

    def signal_group(self, sig: int) -> None:
        # The child is only reaped under the lock, so while reaped is False
        # its pid (= the process group id) cannot have been reused.
        with self.lock:
            if self.reaped:
                return
            try:
                os.killpg(self.proc.pid, sig)
            except ProcessLookupError:
                pass
            except OSError as e:
                log.error("cannot signal %s: %s", self.tile.id, e)


class AppRunner(QObject):
    """Starts tiles' commands, one at a time."""

    started = Signal(object)  # Tile
    finished = Signal(object)  # RunResult

    def __init__(
        self,
        parent: QObject | None = None,
        quick_exit_seconds: float = QUICK_EXIT_SECONDS,
        kill_after_seconds: float = KILL_AFTER_SECONDS,
    ) -> None:
        super().__init__(parent)
        self.quick_exit_seconds = quick_exit_seconds
        self.kill_after_seconds = kill_after_seconds
        self._run: _Run | None = None
        self._done = _Relay(self)
        self._done.result.connect(self._on_done)

    @property
    def running(self) -> Tile | None:
        return self._run.tile if self._run else None

    def start(self, tile: Tile) -> bool:
        """Start tile's command. Returns False if an app is already running."""
        if self._run is not None:
            log.warning("not starting %s: %s is still running", tile.id, self._run.tile.id)
            return False
        log.info("starting %s: %s", tile.id, " ".join(tile.command))
        try:
            proc = subprocess.Popen(
                tile.command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as e:
            log.error("cannot start %s: %s", tile.id, e)
            message = e.strerror or str(e)
            if isinstance(e, FileNotFoundError):
                message = f"Program not found: {tile.command[0]}"
            result = RunResult(tile, None, 0.0, (), stopped=False, error=message,
                               quick_exit_seconds=self.quick_exit_seconds)
            self.started.emit(tile)
            # Report asynchronously, like a real exit, so callers see one order.
            QTimer.singleShot(0, lambda: self.finished.emit(result))
            return True
        run = _Run(tile, proc)
        self._run = run
        assert proc.stdout is not None
        reader = threading.Thread(target=_read, args=(run, proc.stdout), daemon=True,
                                  name=f"read-{tile.id}")
        reader.start()
        threading.Thread(target=self._wait, args=(run, reader), daemon=True,
                         name=f"wait-{tile.id}").start()
        self.started.emit(tile)
        return True

    def stop(self) -> None:
        """SIGTERM the running app's process group; SIGKILL if still there later."""
        run = self._run
        if run is None or run.stopping:
            return
        log.info("stopping %s", run.tile.id)
        run.stopping = True
        run.signal_group(signal.SIGTERM)

        def kill() -> None:
            if self._run is run:
                log.warning("%s did not stop; killing it", run.tile.id)
                run.signal_group(signal.SIGKILL)

        QTimer.singleShot(int(self.kill_after_seconds * 1000), kill)

    def _wait(self, run: _Run, reader: threading.Thread) -> None:
        try:
            pid = run.proc.pid
            # Wait without reaping, so the process group id stays ours.
            while True:
                try:
                    os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)
                    break
                except InterruptedError:
                    continue
                except ChildProcessError:
                    break
            seconds = time.monotonic() - run.started
            # Leftover helpers in the group would hold the screen or the pipe.
            run.signal_group(signal.SIGTERM)
            reader.join(DRAIN_SECONDS)
            if reader.is_alive():
                run.signal_group(signal.SIGKILL)
                reader.join(DRAIN_SECONDS)
            with run.lock:
                returncode = run.proc.wait()
                run.reaped = True
                tail = tuple(run.tail)
            result = RunResult(
                run.tile, returncode, seconds, tail, stopped=run.stopping,
                quick_exit_seconds=self.quick_exit_seconds,
            )
        except Exception as e:  # never leave the launcher stuck on "running"
            log.exception("waiting for %s failed", run.tile.id)
            result = RunResult(run.tile, None, 0.0, (), stopped=run.stopping,
                               error=str(e), quick_exit_seconds=self.quick_exit_seconds)
        self._done.result.emit((run, result))

    def _on_done(self, item: tuple[_Run, RunResult]) -> None:
        run, result = item
        if self._run is run:
            self._run = None
        log.info("%s exited with %s after %.1f s", result.tile.id, result.returncode, result.seconds)
        self.finished.emit(result)


class _Relay(QObject):
    """Carries a result from a worker thread to the UI thread."""

    result = Signal(object)


def _read(run: _Run, pipe: IO[bytes]) -> None:
    prefix = f"[{run.tile.id}] "
    try:
        with pipe:
            for raw in iter(lambda: pipe.readline(4096), b""):
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                with run.lock:
                    run.tail.append(line)
                try:
                    sys.stderr.write(prefix + line + "\n")
                    sys.stderr.flush()
                except (OSError, ValueError):
                    pass
    except Exception:
        log.exception("reading output of %s failed", run.tile.id)
