"""The real launcher in a subprocess (offscreen), driven by the home command."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from ibp_kiosk.ipc import InstanceLock, pid_path, send_home

from .conftest import LAUNCHER_DIR, pid_alive


def poll(predicate: Callable[[], object], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting")
        time.sleep(0.05)


def launcher_env(runtime_dir: Path, config: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        QT_QPA_PLATFORM="offscreen",
        XDG_RUNTIME_DIR=str(runtime_dir),
        IBP_KIOSK_CONFIG=str(config),
        PYTHONPATH=str(LAUNCHER_DIR),
        IBP_KIOSK_POWEROFF="false",
        IBP_KIOSK_REBOOT="false",
    )
    return env


def home(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ibp_kiosk", "home"], env=env,
                          capture_output=True, text=True, timeout=10)


@pytest.fixture
def station(tmp_path: Path, runtime_dir: Path) -> Iterator[tuple[dict[str, str], Path, subprocess.Popen[str]]]:
    """A launcher whose autostart tile writes its pid to a file and sleeps."""
    pidfile = tmp_path / "app.pid"
    config = tmp_path / "station.toml"
    config.write_text(f"""
[station]
name = "Test"
autostart = "app"

[[tile]]
id = "app"
label = "App"
command = ["sh", "-c", "echo $$ > {pidfile}; exec sleep 60"]

[[status]]
label = "Network"
command = ["true"]
""")
    env = launcher_env(runtime_dir, config)
    proc = subprocess.Popen([sys.executable, "-m", "ibp_kiosk"], env=env,
                            stderr=subprocess.PIPE, text=True)
    yield env, pidfile, proc
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def test_home_without_launcher_is_quiet(runtime_dir: Path, tmp_path: Path) -> None:
    result = home(launcher_env(runtime_dir, tmp_path / "none.toml"))
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert send_home() == 0


def test_home_with_stale_pid_file(runtime_dir: Path) -> None:
    pid_path().parent.mkdir(parents=True, exist_ok=True)
    pid_path().write_text("999999\n")  # not locked: no launcher
    assert send_home() == 0


def test_instance_lock(runtime_dir: Path) -> None:
    first = InstanceLock()
    assert first.acquire()
    assert pid_path().read_text().strip() == str(os.getpid())
    # A second launcher (another open file description) is refused.
    assert not InstanceLock().acquire(attempts=1)


def test_home_stops_app_and_launcher_keeps_running(station) -> None:  # type: ignore[no-untyped-def]
    env, pidfile, proc = station
    poll(lambda: pidfile.exists() and pidfile.read_text().strip())
    app_pid = int(pidfile.read_text())
    assert pid_alive(app_pid)

    result = home(env)
    assert result.returncode == 0, result.stderr
    poll(lambda: not pid_alive(app_pid), 8)
    time.sleep(0.5)
    assert proc.poll() is None  # the launcher is still there

    # Home again with nothing running just shows the tiles.
    assert home(env).returncode == 0
    time.sleep(0.5)
    assert proc.poll() is None

    # A second launcher exits at once and leaves the first alone.
    second = subprocess.run([sys.executable, "-m", "ibp_kiosk"], env=env,
                            capture_output=True, text=True, timeout=20)
    assert second.returncode == 0
    assert "already running" in second.stderr
    assert proc.poll() is None

    # SIGTERM ends the launcher cleanly.
    proc.terminate()
    assert proc.wait(10) == 0
    stderr = proc.stderr.read() if proc.stderr else ""
    assert "home" in stderr
    assert "Traceback" not in stderr


def test_sigterm_stops_the_running_app(station) -> None:  # type: ignore[no-untyped-def]
    env, pidfile, proc = station
    poll(lambda: pidfile.exists() and pidfile.read_text().strip())
    app_pid = int(pidfile.read_text())
    proc.terminate()
    assert proc.wait(10) == 0
    assert not pid_alive(app_pid)
