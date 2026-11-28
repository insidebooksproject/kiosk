from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

from ibp_kiosk.app import LOG_FORMAT, JournalFormatter, stderr_is_journal


def record(level: int, msg: str, exc: bool = False) -> logging.LogRecord:
    exc_info = None
    if exc:
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
    return logging.LogRecord("ibp_kiosk", level, __file__, 1, msg, None, exc_info)


@pytest.mark.parametrize(("level", "prefix"), [
    (logging.CRITICAL, "<2>"), (logging.ERROR, "<3>"), (logging.WARNING, "<4>"),
    (logging.INFO, "<6>"), (logging.DEBUG, "<7>"),
])
def test_journal_formatter_prefixes_the_priority(level: int, prefix: str) -> None:
    text = JournalFormatter(LOG_FORMAT).format(record(level, "hello"))
    assert text == f"{prefix}ibp-kiosk-launcher: {logging.getLevelName(level)} hello"


def test_journal_formatter_prefixes_every_traceback_line() -> None:
    lines = JournalFormatter(LOG_FORMAT).format(record(logging.ERROR, "oops", exc=True)).split("\n")
    assert len(lines) > 2
    assert all(line.startswith("<3>") for line in lines)
    assert lines[-1] == "<3>ValueError: boom"


def test_stderr_is_journal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with open(tmp_path / "err", "w") as f:
        monkeypatch.setattr(sys, "stderr", f)
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
        assert not stderr_is_journal()
        st = os.fstat(f.fileno())
        monkeypatch.setenv("JOURNAL_STREAM", f"{st.st_dev}:{st.st_ino}")
        assert stderr_is_journal()
        monkeypatch.setenv("JOURNAL_STREAM", f"{st.st_dev}:{st.st_ino + 1}")
        assert not stderr_is_journal()
