from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from ibp_kiosk.config import Tile
from ibp_kiosk.runner import AppRunner, RunResult

from .conftest import pid_alive


@pytest.fixture
def runner(qapp: object) -> AppRunner:
    return AppRunner(quick_exit_seconds=0.5, kill_after_seconds=1.0)


def run(runner: AppRunner, wait_until: Callable[..., None], *command: str,
        timeout: float = 10.0) -> RunResult:
    results: list[RunResult] = []
    runner.finished.connect(results.append)
    assert runner.start(Tile("t", "Test", tuple(command)))
    wait_until(lambda: results, timeout)
    assert runner.running is None
    return results[0]


def sh(script: str) -> tuple[str, ...]:
    return ("sh", "-c", script)


def test_success(runner: AppRunner, wait_until: Callable[..., None]) -> None:
    result = run(runner, wait_until, *sh("echo hello; sleep 0.7"))
    assert result.returncode == 0
    assert not result.failed
    assert result.tail == ("hello",)


def test_nonzero_exit_fails_with_output(runner: AppRunner, wait_until: Callable[..., None]) -> None:
    result = run(runner, wait_until, *sh("echo out; echo err >&2; sleep 0.7; exit 3"))
    assert result.returncode == 3
    assert result.failed
    assert not result.quick
    assert result.tail == ("out", "err")


def test_quick_exit_fails_even_with_status_zero(runner: AppRunner,
                                                wait_until: Callable[..., None]) -> None:
    result = run(runner, wait_until, "true")
    assert result.returncode == 0
    assert result.quick
    assert result.failed


def test_missing_program(runner: AppRunner, wait_until: Callable[..., None]) -> None:
    result = run(runner, wait_until, "no-such-program-ibp")
    assert result.returncode is None
    assert result.failed
    assert "no-such-program-ibp" in result.error


def test_output_tail_keeps_last_15_lines(runner: AppRunner,
                                         wait_until: Callable[..., None]) -> None:
    result = run(runner, wait_until, *sh("seq 1 100; exit 1"))
    assert result.tail == tuple(str(i) for i in range(86, 101))


def test_lots_of_output_does_not_block(runner: AppRunner, wait_until: Callable[..., None]) -> None:
    # 4 MB, far more than a pipe holds; the child must still finish.
    script = "import sys\nfor i in range(40000): print('x' * 99)\nprint('last')"
    result = run(runner, wait_until, sys.executable, "-c", script, timeout=20)
    assert result.returncode == 0
    assert result.tail[-1] == "last"


def test_output_goes_to_stderr(runner: AppRunner, wait_until: Callable[..., None],
                               capfd: pytest.CaptureFixture[str]) -> None:
    run(runner, wait_until, *sh("echo to-the-journal"))
    assert "[t] to-the-journal" in capfd.readouterr().err


def test_one_app_at_a_time(runner: AppRunner, wait_until: Callable[..., None]) -> None:
    assert runner.start(Tile("a", "A", ("sleep", "30")))
    assert not runner.start(Tile("b", "B", ("true",)))
    assert runner.running is not None and runner.running.id == "a"
    results: list[RunResult] = []
    runner.finished.connect(results.append)
    runner.stop()
    wait_until(lambda: results)


def test_stop_terminates_process_group(runner: AppRunner, wait_until: Callable[..., None],
                                       tmp_path: Path) -> None:
    pidfile = tmp_path / "pid"
    results: list[RunResult] = []
    runner.finished.connect(results.append)
    runner.start(Tile("t", "T", sh(f"sleep 60 & echo $! > {pidfile}; wait")))
    wait_until(lambda: pidfile.exists() and pidfile.read_text().strip())
    grandchild = int(pidfile.read_text())
    started = time.monotonic()
    runner.stop()
    wait_until(lambda: results)
    assert time.monotonic() - started < 1.0  # SIGTERM was enough
    result = results[0]
    assert result.stopped
    assert not result.failed
    wait_until(lambda: not pid_alive(grandchild), 3)


def test_stop_kills_if_sigterm_is_ignored(runner: AppRunner, wait_until: Callable[..., None],
                                          tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    results: list[RunResult] = []
    runner.finished.connect(results.append)
    runner.start(Tile("t", "T", sh(f"trap '' TERM; touch {ready}; sleep 60")))
    wait_until(ready.exists)
    started = time.monotonic()
    runner.stop()
    wait_until(lambda: results, 10)
    elapsed = time.monotonic() - started
    assert 0.9 < elapsed < 5  # kill_after_seconds is 1 here
    assert results[0].stopped
    assert results[0].returncode == -9


def test_leftover_helpers_are_stopped(runner: AppRunner, wait_until: Callable[..., None],
                                      tmp_path: Path) -> None:
    # The app exits but leaves a helper holding the output pipe.
    pidfile = tmp_path / "pid"
    result = run(runner, wait_until, *sh(f"sleep 60 & echo $! > {pidfile}; sleep 0.7"))
    assert result.returncode == 0
    wait_until(lambda: not pid_alive(int(pidfile.read_text())), 3)
