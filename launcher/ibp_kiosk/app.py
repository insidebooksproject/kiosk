"""Start the launcher: lock, config, Qt application, window, signals."""

from __future__ import annotations

import logging
import os
import signal
import socket
import struct
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import config as config_mod
from .ipc import HOME_SIGNAL, InstanceLock
from .ui import MainWindow

log = logging.getLogger("ibp_kiosk")

APP_ID = "ibp-kiosk-launcher"  # Wayland app_id, for labwc window rules


class SignalWatcher(QObject):
    """Turns Unix signals into a Qt signal on the UI thread."""

    received = Signal(int)

    def __init__(self, signums: list[int]) -> None:
        super().__init__()
        self._read, self._write = socket.socketpair()
        self._read.setblocking(False)
        self._write.setblocking(False)
        signal.set_wakeup_fd(self._write.fileno(), warn_on_full_buffer=False)
        for signum in signums:
            signal.signal(signum, lambda *_: None)  # the wakeup fd does the work
        self._notifier = QSocketNotifier(self._read.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._on_readable)

    def _on_readable(self) -> None:
        try:
            data = self._read.recv(64)
        except BlockingIOError:
            return
        for signum in data:
            self.received.emit(signum)


# syslog priorities by logging level, for the journal's PRIORITY (and the
# "<N>" line prefix when the journal's socket can't be used).
_PRIORITIES = ((logging.CRITICAL, 2), (logging.ERROR, 3), (logging.WARNING, 4),
               (logging.INFO, 6))
LOG_FORMAT = "ibp-kiosk-launcher: %(levelname)s %(message)s"
JOURNAL_SOCKET = "/run/systemd/journal/socket"
# The session's identifier (ibp-kiosk-session's systemd-cat -t), which
# `journalctl -t ibp-kiosk` and the station's log upload look for.
JOURNAL_IDENTIFIER = "ibp-kiosk"
# The log upload exports fields of up to 4096 bytes (bigger ones as null).
MAX_MESSAGE_BYTES = 4000


def priority(levelno: int) -> int:
    """The syslog priority of a logging level (3 for ERROR)."""
    return next((p for level, p in _PRIORITIES if levelno >= level), 7)


def stderr_is_journal() -> bool:
    """Whether stderr is a journal stream, as under ``systemd-cat`` (the session)."""
    stream = os.environ.get("JOURNAL_STREAM", "")
    if not stream:
        return False
    try:
        st = os.fstat(sys.stderr.fileno())
    except (OSError, ValueError, AttributeError):
        return False
    return stream == f"{st.st_dev}:{st.st_ino}"


def with_priority(text: str, levelno: int) -> str:
    """Each line of ``text`` started with its syslog priority (``<3>`` for
    ERROR), which journald reads from a stream; each line is then an entry of
    its own, so this is only :class:`JournalHandler`'s fallback."""
    prefix = f"<{priority(levelno)}>"
    return "\n".join(prefix + line for line in text.split("\n"))


def fit_message(text: str, limit: int = MAX_MESSAGE_BYTES) -> str:
    """``text`` cut to ``limit`` UTF-8 bytes: its first line and as many of its
    last lines (a traceback's innermost frames and exception) as fit."""
    if len(text.encode()) <= limit:
        return text
    lines = text.split("\n")
    head = lines[0].encode()[: limit // 2].decode(errors="ignore")
    tail: list[str] = []
    for line in reversed(lines[1:]):
        marker = f"[{len(lines) - 2 - len(tail)} lines left out]"
        if len("\n".join([head, marker, line, *tail]).encode()) > limit:
            break
        tail.insert(0, line)
    return "\n".join([head, f"[{len(lines) - 1 - len(tail)} lines left out]", *tail])


def journal_datagram(fields: dict[str, str]) -> bytes:
    """``fields`` in journald's native protocol (a value with a newline in
    it goes as its length and bytes)."""
    out = bytearray()
    for key, value in fields.items():
        data = value.encode()
        if b"\n" in data:
            out += key.encode() + b"\n" + struct.pack("<Q", len(data)) + data + b"\n"
        else:
            out += key.encode() + b"=" + data + b"\n"
    return bytes(out)


class JournalHandler(logging.Handler):
    """Writes each record to the journal as one entry, traceback included.

    Through journald's socket, at the record's priority, with the session's
    identifier and the record's CODE_FILE, CODE_LINE and CODE_FUNC, so the
    station's log upload exports a traceback as one entry and not one per
    line. If the socket can't take it, the record goes to stderr (the
    session's journal stream) one prefixed line at a time instead.
    """

    def __init__(self, path: str = JOURNAL_SOCKET) -> None:
        super().__init__()
        self.path = path
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)  # never hold up the UI

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
            fields = {
                "MESSAGE": fit_message(text),
                "PRIORITY": str(priority(record.levelno)),
                "SYSLOG_IDENTIFIER": JOURNAL_IDENTIFIER,
                "CODE_FILE": record.pathname,
                "CODE_LINE": str(record.lineno),
                "CODE_FUNC": record.funcName or "",
            }
            datagram = journal_datagram({k: v for k, v in fields.items() if v})
        except Exception:  # noqa: BLE001
            self.handleError(record)
            return
        try:
            self.socket.sendto(datagram, self.path)
        except OSError:
            try:
                sys.stderr.write(with_priority(text, record.levelno) + "\n")
                sys.stderr.flush()
            except Exception:  # noqa: BLE001
                self.handleError(record)

    def close(self) -> None:
        self.socket.close()
        super().close()


def configure_logging() -> None:
    if stderr_is_journal():
        handler: logging.Handler = JournalHandler()
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _log_unexpected(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
    log.error("unexpected error", exc_info=(exc_type, exc, tb))


def run(config_path: Path, windowed: bool = False) -> int:
    configure_logging()
    # Never let a bug in a slot or a worker thread end the session.
    sys.excepthook = _log_unexpected
    threading.excepthook = lambda args: _log_unexpected(args.exc_type, args.exc_value,
                                                        args.exc_traceback)

    lock = InstanceLock()
    try:
        if not lock.acquire():
            log.info("another launcher is already running in this session")
            return 0
    except OSError as e:
        log.error("cannot set up the instance lock (%s); Home key will not work", e)

    config: config_mod.Config | None = None
    error = ""
    try:
        config = config_mod.load(config_path)
    except config_mod.ConfigError as e:
        error = str(e)
        log.error("bad config: %s", error)

    QGuiApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow(config, error, windowed=windowed)
    if windowed:
        window.resize(1366, 768)
    window.bring_to_front()

    def on_signal(signum: int) -> None:
        if signum == HOME_SIGNAL:
            window.go_home()
        else:
            log.info("got signal %d; stopping", signum)
            window.quit_gracefully(app.quit)

    watcher = SignalWatcher([HOME_SIGNAL, signal.SIGTERM, signal.SIGINT, signal.SIGHUP])
    watcher.received.connect(on_signal)

    if config is not None:
        window.monitor.start()
        if config.autostart:
            tile = config.tile(config.autostart)
            QTimer.singleShot(0, lambda: window.start_tile(tile))

    status = app.exec()
    log.info("exiting")
    return status
