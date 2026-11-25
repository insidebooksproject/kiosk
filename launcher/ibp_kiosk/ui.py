"""The launcher window: header, pages (tiles, running, failure, ...), status strip."""

from __future__ import annotations

import logging
import os
import shlex
import socket
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import Config, Tile
from .runner import AppRunner, RunResult
from .status import CheckResult, StatusMonitor

log = logging.getLogger(__name__)

ADMIN_KEY = "Ctrl+Alt+A"
RUNNING_AFTER_MS = 2000  # "Starting X..." becomes "X is running" after this
POWER_COMMANDS = {
    "poweroff": ("IBP_KIOSK_POWEROFF", ["systemctl", "poweroff"]),
    "reboot": ("IBP_KIOSK_REBOOT", ["systemctl", "reboot"]),
}

STYLE = """
QWidget#root { background: #14213d; }
QLabel { color: #ffffff; background: transparent; }
QLabel#station { font-size: 34px; font-weight: bold; }
QLabel#heading { font-size: 40px; font-weight: bold; }
QLabel#sentence { font-size: 28px; }
QLabel#small { font-size: 20px; }
QLabel#info { font-size: 22px; }
QLabel#tail {
    font-family: "DejaVu Sans Mono", monospace; font-size: 16px;
    color: #111111; background: #ffffff; padding: 12px; border-radius: 6px;
}
QPushButton {
    font-size: 24px; color: #111111; background: #e6e6e6;
    border: 4px solid #e6e6e6; border-radius: 10px; padding: 10px 24px;
}
QPushButton:hover { background: #cfe0ff; border-color: #cfe0ff; }
QPushButton:pressed { background: #a9c7ff; }
QPushButton:focus { border: 6px solid #ffc300; }
QPushButton#tile { background: #ffffff; border-color: #ffffff; padding: 16px; }
QPushButton#tile:hover { background: #cfe0ff; border-color: #cfe0ff; }
QPushButton#tile:pressed { background: #a9c7ff; }
QPushButton#tile:focus { border: 8px solid #ffc300; }
QPushButton#tile QLabel { color: #111111; }
QLabel#tileLabel { font-size: 34px; font-weight: bold; }
QLabel#tileDescription { font-size: 21px; }
QLabel#tileNumber { font-size: 18px; color: #444444; }
QFrame#strip { background: #0b1427; }
QLabel#chip {
    font-size: 20px; color: #111111; background: #ffffff;
    border-radius: 8px; padding: 6px 14px;
}
QLabel#chip[state="bad"] { background: #ffd7d7; border: 3px solid #c62828; }
"""


class Button(QPushButton):
    """A push button that Enter and Return also press."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers():
            self.click()
        else:
            super().keyPressEvent(event)


class TileButton(Button):
    def __init__(self, tile: Tile, number: int | None, grid: TileGrid) -> None:
        super().__init__()
        self.tile = tile
        self._grid = grid
        self.setObjectName("tile")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(260, 130)
        self.setAccessibleName(tile.label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 16)
        number_label = QLabel(str(number) if number else "")
        number_label.setObjectName("tileNumber")
        layout.addWidget(number_label, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        for text, name in ((tile.label, "tileLabel"), (tile.description, "tileDescription")):
            if not text:
                continue
            label = QLabel(text)
            label.setObjectName(name)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        layout.addStretch(1)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        moves = {
            Qt.Key.Key_Left: (0, -1),
            Qt.Key.Key_Right: (0, 1),
            Qt.Key.Key_Up: (-1, 0),
            Qt.Key.Key_Down: (1, 0),
        }
        if event.key() in moves and not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
            self._grid.move_focus(self, *moves[event.key()])
        else:
            super().keyPressEvent(event)


class TileGrid(QWidget):
    """Tiles in rows; arrow keys move between them, 1-9 pick one."""

    chosen = Signal(object)  # Tile

    def __init__(self, tiles: tuple[Tile, ...]) -> None:
        super().__init__()
        n = len(tiles)
        self.columns = n if n <= 3 else 2 if n == 4 else 3
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        self.buttons: list[TileButton] = []
        for i, tile in enumerate(tiles):
            button = TileButton(tile, i + 1 if i < 9 else None, self)
            button.clicked.connect(lambda _=False, t=tile: self.chosen.emit(t))
            layout.addWidget(button, i // self.columns, i % self.columns)
            self.buttons.append(button)
        for c in range(self.columns):
            layout.setColumnStretch(c, 1)
        for r in range((n + self.columns - 1) // self.columns):
            layout.setRowStretch(r, 1)

    def move_focus(self, button: TileButton, drow: int, dcol: int) -> None:
        i = self.buttons.index(button)
        row, col = divmod(i, self.columns)
        row, col = row + drow, col + dcol
        if not 0 <= col < self.columns or row < 0:
            return
        target = min(row * self.columns + col, len(self.buttons) - 1)
        if target // self.columns == row:
            self.buttons[target].setFocus(Qt.FocusReason.OtherFocusReason)

    def choose_number(self, number: int) -> bool:
        if 1 <= number <= min(9, len(self.buttons)):
            self.buttons[number - 1].click()
            return True
        return False

    def focus(self, tile: Tile | None = None) -> None:
        for button in self.buttons:
            if tile is None or button.tile == tile:
                button.setFocus(Qt.FocusReason.OtherFocusReason)
                return
        if self.buttons:
            self.buttons[0].setFocus(Qt.FocusReason.OtherFocusReason)


class StatusStrip(QFrame):
    def __init__(self, config: Config | None) -> None:
        super().__init__()
        self.setObjectName("strip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(16)
        self.chips: list[QLabel] = []
        self.labels: list[str] = []
        for check in config.statuses if config else ():
            chip = QLabel()
            chip.setObjectName("chip")
            self.labels.append(check.label)
            self.chips.append(chip)
            layout.addWidget(chip)
            self._show(len(self.chips) - 1, "…", "Checking", None)
        layout.addStretch(1)
        self.setVisible(bool(self.chips))

    def set_result(self, index: int, result: CheckResult) -> None:
        if result.ok:
            self._show(index, '<span style="color:#1b7a2f">✓</span>', result.text or "OK", True)
        else:
            self._show(index, '<span style="color:#c62828">✗</span>', result.text or "Problem", False)

    def _show(self, index: int, symbol: str, text: str, ok: bool | None) -> None:
        chip = self.chips[index]
        chip.setText(f"{symbol} <b>{_html(self.labels[index])}:</b> {_html(text)}")
        chip.setProperty("state", "bad" if ok is False else "good")
        chip.style().unpolish(chip)
        chip.style().polish(chip)


class _Relay(QObject):
    power_failed = Signal(str)


class MainWindow(QWidget):
    def __init__(self, config: Config | None, config_error: str = "",
                 runner: AppRunner | None = None, windowed: bool = False) -> None:
        super().__init__()
        self.config = config
        self.windowed = windowed
        self.quitting = False
        self.runner = runner or AppRunner(self)
        self.runner.started.connect(self._on_started)
        self.runner.finished.connect(self._on_finished)
        self._last_tile: Tile | None = None
        self._before_confirm: QWidget | None = None
        self._power_action = ""
        self._relay = _Relay(self)
        self._relay.power_failed.connect(self._on_power_failed)

        self.setObjectName("root")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("IBP")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(32, 20, 32, 8)
        self.station = QLabel(config.name if config else socket.gethostname())
        self.station.setObjectName("station")
        header.addWidget(self.station)
        header.addStretch(1)
        self.restart_button = Button("Restart")
        self.restart_button.clicked.connect(lambda: self.ask_power("reboot"))
        self.shutdown_button = Button("Shut down")
        self.shutdown_button.clicked.connect(lambda: self.ask_power("poweroff"))
        header.addWidget(self.restart_button)
        header.addSpacing(16)
        header.addWidget(self.shutdown_button)
        root.addLayout(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.strip = StatusStrip(config)
        root.addWidget(self.strip)

        self.grid = TileGrid(config.tiles if config else ())
        self.grid.chosen.connect(self.start_tile)
        self.tiles_page = _page(self.grid, margins=(32, 16, 32, 24))

        self._build_running_page()
        self._build_failure_page()
        self._build_confirm_page()
        self._build_admin_page()
        self._build_message_page()
        self.error_page = self._message_page(
            "This computer isn't set up correctly.",
            "Tell a coordinator.",
            config_error,
        )

        self.monitor = StatusMonitor(config.statuses if config else (), self)
        self.monitor.result.connect(self.strip.set_result)

        shortcut = QShortcut(QKeySequence(ADMIN_KEY), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(self.show_admin)

        self.show_home()

    # Pages

    def _build_running_page(self) -> None:
        self.running_title = _label("", "heading")
        self.running_hint = _label("To close it and come back here, press the Home key.", "sentence")
        self.close_button = Button("Close")
        self.close_button.clicked.connect(self.runner.stop)
        self.running_page = _page(
            self.running_title, self.running_hint, _centered(self.close_button), center=True
        )

    def _build_failure_page(self) -> None:
        self.failure_title = _label("", "heading")
        self.failure_sentence = _label("", "sentence")
        self.failure_detail = _label("", "small")
        self.failure_tail = _label("", "tail")
        self.failure_tail.setTextFormat(Qt.TextFormat.PlainText)
        self.failure_tail.setWordWrap(True)
        self.failure_tail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.failure_tail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.failure_back = Button("Back to start")
        self.failure_back.clicked.connect(self.show_home)
        self.failure_page = _page(
            self.failure_title, self.failure_sentence, self.failure_tail,
            self.failure_detail, _centered(self.failure_back),
        )

    def _build_confirm_page(self) -> None:
        self.confirm_title = _label("", "heading")
        self.confirm_yes = Button("")
        self.confirm_yes.clicked.connect(self.do_power)
        self.confirm_no = Button("No, go back")
        self.confirm_no.clicked.connect(self._cancel_power)
        self.confirm_page = _page(
            self.confirm_title, _centered(self.confirm_yes, self.confirm_no), center=True
        )

    def _build_admin_page(self) -> None:
        self.admin_info = _label("", "info")
        self.admin_info.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.admin_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.admin_grid = TileGrid(self.config.admin if self.config else ())
        self.admin_grid.chosen.connect(self.start_tile)
        back = Button("Back")
        back.clicked.connect(self.show_home)
        title = _label("Admin", "heading")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.admin_back = back
        self.admin_page = _page(title, self.admin_info, self.admin_grid, _centered(back))

    def _build_message_page(self) -> None:
        self.message_title = _label("", "heading")
        self.message_page = _page(self.message_title, center=True)

    def _message_page(self, title: str, sentence: str, detail: str) -> QWidget:
        small = _label(detail, "small")
        small.setTextFormat(Qt.TextFormat.PlainText)
        return _page(_label(title, "heading"), _label(sentence, "sentence"), small, center=True)

    def _show(self, page: QWidget, focus: QWidget | None = None) -> None:
        if self.stack.indexOf(page) < 0:
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        idle = self.runner.running is None and page is not self.message_page
        self.restart_button.setVisible(idle)
        self.shutdown_button.setVisible(idle)
        if focus is not None:
            focus.setFocus(Qt.FocusReason.OtherFocusReason)

    @property
    def page(self) -> QWidget:
        return self.stack.currentWidget()

    # Actions

    def show_home(self) -> None:
        if self.config is None:
            self._show(self.error_page, self.shutdown_button)
            return
        self._show(self.tiles_page)
        self.grid.focus(self._last_tile)

    def go_home(self) -> None:
        """The Home key: close the running app, or just show the tiles."""
        log.info("home")
        if self.runner.running is not None:
            self.runner.stop()  # its finished signal brings the tiles back
        elif self.page is not self.message_page:
            self.show_home()
        self.bring_to_front()

    def bring_to_front(self) -> None:
        if self.windowed:
            self.show()
        else:
            self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def start_tile(self, tile: Tile) -> None:
        if self.runner.running is not None or self.quitting:
            return
        self._last_tile = tile
        self.runner.start(tile)

    def _on_started(self, tile: Tile) -> None:
        self.running_title.setText(f"Starting {tile.label}…")
        self.close_button.setText(f"Close {tile.label}")
        self._show(self.running_page, self.close_button)

        def now_running() -> None:
            if self.runner.running == tile and self.page is self.running_page:
                self.running_title.setText(f"{tile.label} is running")

        QTimer.singleShot(RUNNING_AFTER_MS, now_running)

    def _on_finished(self, result: RunResult) -> None:
        if self.quitting:
            return
        if result.failed:
            self.show_failure(result)
        else:
            self.show_home()

    def show_failure(self, result: RunResult) -> None:
        self.failure_title.setText(result.tile.label)
        if result.quick:
            self.failure_sentence.setText("This didn't start. Tell a coordinator.")
        else:
            self.failure_sentence.setText("This stopped because of a problem. Tell a coordinator.")
        lines = list(result.tail)
        if result.error:
            lines.append(result.error)
        self.failure_tail.setText("\n".join(lines) or "(It printed nothing.)")
        if result.returncode is None:
            self.failure_detail.setText("")
        elif result.returncode < 0:
            self.failure_detail.setText(f"It was stopped by signal {-result.returncode}.")
        else:
            self.failure_detail.setText(f"Exit code {result.returncode}.")
        self._show(self.failure_page, self.failure_back)
        self.bring_to_front()

    def show_admin(self) -> None:
        if self.runner.running is not None or self.page is self.message_page:
            return
        self.admin_info.setText(_admin_info())
        self._show(self.admin_page)
        if self.admin_grid.buttons:
            self.admin_grid.focus()
        else:
            self.admin_back.setFocus()

    def ask_power(self, action: str) -> None:
        if self.runner.running is not None:
            return
        self._power_action = action
        self._before_confirm = self.page
        if action == "poweroff":
            self.confirm_title.setText("Shut down this computer?")
            self.confirm_yes.setText("Yes, shut down")
        else:
            self.confirm_title.setText("Restart this computer?")
            self.confirm_yes.setText("Yes, restart")
        self._show(self.confirm_page, self.confirm_no)

    def _cancel_power(self) -> None:
        if self._before_confirm in (None, self.tiles_page, self.error_page):
            self.show_home()
        else:
            self._show(self._before_confirm, None)
            self._before_confirm.focusNextChild()

    def do_power(self) -> None:
        action = self._power_action
        command = power_command(action)
        self.message_title.setText("Shutting down…" if action == "poweroff" else "Restarting…")
        self._show(self.message_page)
        log.info("%s: %s", action, " ".join(command))

        def work() -> None:
            try:
                proc = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                      timeout=60, start_new_session=True)
                output = (proc.stdout + proc.stderr).decode(errors="replace").strip()
                if proc.returncode != 0:
                    log.error("%s failed (%d): %s", action, proc.returncode, output)
                    self._relay.power_failed.emit(output or f"Exit code {proc.returncode}.")
            except Exception as e:
                log.error("%s failed: %s", action, e)
                self._relay.power_failed.emit(str(e))

        threading.Thread(target=work, daemon=True, name="power").start()

    def _on_power_failed(self, output: str) -> None:
        label = "Shut down" if self._power_action == "poweroff" else "Restart"
        result = RunResult(Tile("power", label, ()), None, 0.0, tuple(output.splitlines()[-15:]),
                           stopped=False)
        self.show_failure(result)
        self.failure_sentence.setText("This didn't work. Tell a coordinator.")

    def quit_gracefully(self, quit_app: Callable[[], None]) -> None:
        """Stop the running app (if any), then call quit_app."""
        if self.quitting:
            return
        self.quitting = True
        if self.runner.running is None:
            quit_app()
            return
        self.runner.finished.connect(lambda _result: quit_app())
        self.runner.stop()
        QTimer.singleShot(int(self.runner.kill_after_seconds * 1000) + 3000, quit_app)

    # Events

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9 and not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
            number = key - Qt.Key.Key_0
            if self.page is self.tiles_page and self.grid.choose_number(number):
                return
            if self.page is self.admin_page and self.admin_grid.choose_number(number):
                return
        if key == Qt.Key.Key_Escape:
            if self.page is self.confirm_page:
                self._cancel_power()
                return
            if self.page in (self.admin_page, self.failure_page):
                self.show_home()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        # Volunteers must not be able to close the launcher by accident.
        if self.windowed or self.quitting:
            event.accept()
        else:
            event.ignore()


def power_command(action: str) -> list[str]:
    env, default = POWER_COMMANDS[action]
    value = os.environ.get(env, "").strip()
    return shlex.split(value) if value else default


def _admin_info() -> str:
    addresses = []
    for iface in QNetworkInterface.allInterfaces():
        if iface.flags() & QNetworkInterface.InterfaceFlag.IsLoopBack:
            continue
        for entry in iface.addressEntries():
            ip = entry.ip()
            if ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol or (
                ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv6Protocol
                and ip.isGlobal() and not ip.isUniqueLocalUnicast()
            ):
                addresses.append(f"{_html(iface.name())} {_html(ip.toString())}")
    version = f"launcher {__version__}"
    try:
        version += f", Debian {Path('/etc/debian_version').read_text().strip()}"
    except OSError:
        pass
    rows = [
        ("Computer name", _html(socket.gethostname())),
        ("Addresses", "<br>".join(addresses) or "none"),
        ("Version", _html(version)),
    ]
    cells = "".join(
        f'<tr><td style="padding-right:24px; vertical-align:top"><b>{k}</b></td><td>{v}</td></tr>'
        for k, v in rows
    )
    return f"<table>{cells}</table>"


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _centered(*widgets: QWidget) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 16, 0, 0)
    layout.setSpacing(24)
    layout.addStretch(1)
    for widget in widgets:
        widget.setMinimumHeight(64)
        layout.addWidget(widget)
    layout.addStretch(1)
    return row


def _page(*widgets: QWidget, center: bool = False,
          margins: tuple[int, int, int, int] = (48, 16, 48, 24)) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(*margins)
    layout.setSpacing(20)
    if center:
        layout.addStretch(1)
    for widget in widgets:
        layout.addWidget(widget)
    if center:
        layout.addStretch(1)
    return page
