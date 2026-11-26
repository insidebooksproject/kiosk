from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ibp_kiosk.config import Config, StatusCheck, Tile
from ibp_kiosk.runner import AppRunner
from ibp_kiosk.status import CheckResult
from ibp_kiosk.ui import ADMIN_KEY, MainWindow, power_command

TILES = (
    Tile("ok", "Works", ("sleep", "30"), "Runs for a while"),
    Tile("bad", "Broken", ("sh", "-c", "echo oh no; exit 4")),
    Tile("c", "Third", ("true",)),
    Tile("d", "Fourth", ("true",)),
    Tile("e", "Fifth", ("true",)),
)
CONFIG = Config(
    name="Test station",
    tiles=TILES,
    statuses=(StatusCheck("Network", ("true",)), StatusCheck("Label printer", ("true",))),
    admin=(Tile("adm", "Admin thing", ("sleep", "30")),),
)


@pytest.fixture
def window(qapp: QApplication) -> Iterator[MainWindow]:
    w = MainWindow(CONFIG, runner=AppRunner(quick_exit_seconds=0.5, kill_after_seconds=1),
                   windowed=True)
    w.resize(1366, 768)
    w.show()
    w.activateWindow()
    assert QTest.qWaitForWindowActive(w)
    yield w
    w.close()
    w.deleteLater()


def key(window: MainWindow, k: Qt.Key, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
    target = QApplication.focusWidget() or window
    QTest.keyClick(target, k, modifiers)


def admin_key(window: MainWindow) -> None:
    # Through the window, like a real key press, so shortcuts are matched.
    QTest.keySequence(window.windowHandle(), QKeySequence(ADMIN_KEY))


def test_tiles_shown_with_station_name(window: MainWindow) -> None:
    assert window.page is window.tiles_page
    assert window.station.text() == "Test station"
    assert [b.tile.id for b in window.grid.buttons] == ["ok", "bad", "c", "d", "e"]
    assert window.grid.columns == 3
    assert window.grid.buttons[0].hasFocus()


def test_arrow_keys_move_focus(window: MainWindow) -> None:
    buttons = window.grid.buttons
    key(window, Qt.Key.Key_Right)
    assert buttons[1].hasFocus()
    key(window, Qt.Key.Key_Down)
    assert buttons[4].hasFocus()
    key(window, Qt.Key.Key_Right)  # no tile there
    assert buttons[4].hasFocus()
    key(window, Qt.Key.Key_Left)
    assert buttons[3].hasFocus()
    key(window, Qt.Key.Key_Up)
    assert buttons[0].hasFocus()


def test_number_key_starts_tile_and_home_stops_it(window: MainWindow,
                                                  wait_until: Callable[..., None]) -> None:
    key(window, Qt.Key.Key_1)
    assert window.runner.running == TILES[0]
    assert window.page is window.running_page
    assert "Starting Works" in window.running_title.text()
    assert not window.shutdown_button.isVisible()
    window.go_home()
    wait_until(lambda: window.page is window.tiles_page)
    assert window.runner.running is None
    assert window.grid.buttons[0].hasFocus()


def test_enter_starts_focused_tile(window: MainWindow, wait_until: Callable[..., None]) -> None:
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Return)
    assert window.runner.running == TILES[1]
    wait_until(lambda: window.page is window.failure_page)
    assert window.failure_title.text() == "Broken"
    assert "didn't start" in window.failure_sentence.text()
    assert window.failure_tail.toPlainText() == "oh no"
    assert window.failure_detail.text() == "Exit code 4."
    assert window.failure_back.hasFocus()
    key(window, Qt.Key.Key_Return)
    assert window.page is window.tiles_page
    assert window.grid.buttons[1].hasFocus()


def test_home_closes_failure_page(window: MainWindow, wait_until: Callable[..., None]) -> None:
    window.start_tile(TILES[1])
    wait_until(lambda: window.page is window.failure_page)
    window.go_home()
    assert window.page is window.tiles_page


def test_admin_screen(window: MainWindow, wait_until: Callable[..., None]) -> None:
    admin_key(window)
    assert window.page is window.admin_page
    assert "Computer name" in window.admin_info.text()
    assert "launcher" in window.admin_info.text()
    assert [b.tile.id for b in window.admin_grid.buttons] == ["adm"]
    key(window, Qt.Key.Key_1)
    assert window.runner.running is not None and window.runner.running.id == "adm"
    admin_key(window)  # not while an app runs
    assert window.page is window.running_page
    window.go_home()
    wait_until(lambda: window.page is window.tiles_page)
    admin_key(window)
    key(window, Qt.Key.Key_Escape)
    assert window.page is window.tiles_page


def test_status_strip(window: MainWindow) -> None:
    chip = window.strip.chips[0]
    assert "Network" in chip.text() and chip.toolTip() == "Network: Checking"
    window.strip.set_result(0, CheckResult(True, "Wi-Fi Vesper"))
    assert "✓" in chip.text() and "Vesper" not in chip.text()
    assert chip.toolTip() == "Network: Wi-Fi Vesper"
    window.strip.set_result(0, CheckResult(False, "Not connected"))
    assert "✗" in chip.text() and chip.toolTip() == "Network: Not connected"
    assert chip.property("state") == "bad"


def test_status_chips_share_the_width(window: MainWindow) -> None:
    window.strip.set_result(0, CheckResult(True, "Cable"))
    window.strip.set_result(1, CheckResult(False, "Plugged in, but not detected (try replugging it)"))
    QTest.qWait(50)
    first, second = window.strip.chips
    assert abs(first.width() - second.width()) <= 1
    assert first.height() == second.height()
    assert first.x() + first.width() < second.x() and second.geometry().right() < window.width()


def test_power_confirm_and_cancel(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBP_KIOSK_POWEROFF", "true")
    window.shutdown_button.click()
    assert window.page is window.confirm_page
    assert window.confirm_no.hasFocus()  # the safe choice is the default
    assert not window.shutdown_button.isVisible()
    key(window, Qt.Key.Key_Escape)
    assert window.page is window.tiles_page
    window.shutdown_button.click()
    window.confirm_yes.click()
    assert window.page is window.message_page
    assert window.message_title.text() == "Shutting down…"


def test_power_failure_is_shown(window: MainWindow, monkeypatch: pytest.MonkeyPatch,
                                wait_until: Callable[..., None]) -> None:
    monkeypatch.setenv("IBP_KIOSK_REBOOT", "sh -c 'echo Access denied >&2; exit 1'")
    window.restart_button.click()
    assert window.confirm_title.text() == "Restart this computer?"
    window.confirm_yes.click()
    wait_until(lambda: window.page is window.failure_page)
    assert window.failure_title.text() == "Restart"
    assert "Access denied" in window.failure_tail.toPlainText()


def test_power_command_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBP_KIOSK_POWEROFF", raising=False)
    monkeypatch.delenv("IBP_KIOSK_REBOOT", raising=False)
    assert power_command("poweroff") == ["systemctl", "poweroff"]
    assert power_command("reboot") == ["systemctl", "reboot"]


def test_config_error_page(qapp: QApplication) -> None:
    w = MainWindow(None, "/etc/ibp-kiosk/station.toml does not exist.", windowed=True)
    w.show()
    w.activateWindow()
    assert QTest.qWaitForWindowActive(w)
    assert w.page is w.error_page
    assert w.shutdown_button.isVisible() and w.restart_button.isVisible()
    w.go_home()
    assert w.page is w.error_page
    admin_key(w)
    assert w.page is w.admin_page  # hostname and addresses still useful
    w.go_home()
    assert w.page is w.error_page
    w.close()


def test_close_is_ignored_unless_windowed(qapp: QApplication, tmp_path: Path) -> None:
    w = MainWindow(CONFIG)
    w.show()
    assert not w.close()
    w.quitting = True
    assert w.close()
