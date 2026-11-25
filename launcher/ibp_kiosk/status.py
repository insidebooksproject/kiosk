"""Status strip checks, run off the UI thread on a timer."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from .config import StatusCheck

log = logging.getLogger(__name__)

CHECK_TIMEOUT = 10.0
MAX_TEXT = 60


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    text: str


def run_check(command: tuple[str, ...], timeout: float = CHECK_TIMEOUT) -> CheckResult:
    """Run one check. Exit 0 is fine; the first line of stdout is the text."""
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as e:
        log.error("status check %s cannot run: %s", command[0], e)
        return CheckResult(False, "Check could not run")
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        log.error("status check %s timed out after %.0f s", " ".join(command), timeout)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            pass  # a helper escaped the group and holds the pipe
        proc.wait()
        return CheckResult(False, "No answer")
    if err.strip():
        log.info("status check %s: %s", command[0], err.decode(errors="replace").strip())
    lines = out.decode("utf-8", errors="replace").strip().splitlines()
    text = lines[0].strip() if lines else ""
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 1] + "…"
    if proc.returncode != 0 and not text:
        text = "Problem"
    return CheckResult(proc.returncode == 0, text)


class StatusMonitor(QObject):
    """Runs each check every interval seconds; emits (index, CheckResult)."""

    result = Signal(int, object)
    _finished = Signal(int, object)  # from the worker thread, queued to the UI thread

    def __init__(self, checks: tuple[StatusCheck, ...], parent: QObject | None = None,
                 timeout: float = CHECK_TIMEOUT) -> None:
        super().__init__(parent)
        self._checks = checks
        self._timeout = timeout
        self._busy = [False] * len(checks)
        self._timers: list[QTimer] = []
        self._finished.connect(self._on_finished)
        for i, check in enumerate(checks):
            timer = QTimer(self)
            timer.setInterval(int(check.interval * 1000))
            timer.timeout.connect(lambda i=i: self.run(i))
            self._timers.append(timer)

    def start(self) -> None:
        for i, timer in enumerate(self._timers):
            timer.start()
            self.run(i)

    def run(self, index: int) -> None:
        if self._busy[index]:
            return  # the last run of this check has not finished yet
        self._busy[index] = True
        threading.Thread(target=self._work, args=(index,), daemon=True,
                         name=f"status-{index}").start()

    def _work(self, index: int) -> None:
        try:
            result = run_check(self._checks[index].command, self._timeout)
        except Exception:
            log.exception("status check %d failed", index)
            result = CheckResult(False, "Check could not run")
        self._finished.emit(index, result)

    def _on_finished(self, index: int, result: CheckResult) -> None:
        self._busy[index] = False
        self.result.emit(index, result)