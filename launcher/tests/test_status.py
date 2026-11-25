from __future__ import annotations

import time
from collections.abc import Callable

from ibp_kiosk.config import StatusCheck
from ibp_kiosk.status import CheckResult, StatusMonitor, run_check


def test_ok_with_first_line() -> None:
    assert run_check(("sh", "-c", "echo '  Connected '; echo more")) == CheckResult(True, "Connected")


def test_ok_without_output() -> None:
    assert run_check(("true",)) == CheckResult(True, "")


def test_problem_with_text() -> None:
    assert run_check(("sh", "-c", "echo 'No printer'; exit 1")) == CheckResult(False, "No printer")


def test_problem_without_text() -> None:
    assert run_check(("false",)) == CheckResult(False, "Problem")


def test_missing_program() -> None:
    assert run_check(("no-such-check-ibp",)) == CheckResult(False, "Check could not run")


def test_timeout_kills_the_check() -> None:
    started = time.monotonic()
    result = run_check(("sh", "-c", "sleep 30 & sleep 30"), timeout=0.5)
    assert result == CheckResult(False, "No answer")
    assert time.monotonic() - started < 3


def test_long_text_is_cut() -> None:
    result = run_check(("sh", "-c", "printf '%0100d\\n' 0"))
    assert len(result.text) == 60
    assert result.text.endswith("…")


def test_monitor_runs_checks_without_blocking(wait_until: Callable[..., None]) -> None:
    checks = (
        StatusCheck("Fast", ("sh", "-c", "echo fine"), interval=1),
        StatusCheck("Slow", ("sleep", "5"), interval=1),
    )
    monitor = StatusMonitor(checks, timeout=0.5)
    results: list[tuple[int, CheckResult]] = []
    monitor.result.connect(lambda i, r: results.append((i, r)))
    started = time.monotonic()
    monitor.start()
    assert time.monotonic() - started < 0.2  # start() returns at once
    wait_until(lambda: (0, CheckResult(True, "fine")) in results, 5)
    wait_until(lambda: (1, CheckResult(False, "No answer")) in results, 5)
    # The timer repeats the fast check.
    wait_until(lambda: [i for i, _ in results].count(0) >= 2, 5)
