"""Start the launcher: lock, config, Qt application, window, signals."""

from __future__ import annotations

import logging
import signal
import socket
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


def _log_unexpected(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
    log.error("unexpected error", exc_info=(exc_type, exc, tb))


def run(config_path: Path, windowed: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="ibp-kiosk-launcher: %(levelname)s %(message)s")
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
