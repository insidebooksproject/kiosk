from __future__ import annotations

import logging
import os
import socket
import struct
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from ibp_kiosk.app import LOG_FORMAT, JournalHandler, fit_message, stderr_is_journal


def record(level: int, msg: str, exc: bool = False) -> logging.LogRecord:
    exc_info = None
    if exc:
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
    return logging.LogRecord("ibp_kiosk", level, __file__, 1, msg, None, exc_info)


def parse_datagram(data: bytes) -> dict[str, str]:
    """journald's native protocol, as journald reads it."""
    fields: dict[str, str] = {}
    while data:
        line, sep, rest = data.partition(b"\n")
        assert sep
        if b"=" in line:
            key, _, value = line.partition(b"=")
            data = rest
        else:
            key = line
            size = struct.unpack("<Q", rest[:8])[0]
            value, data = rest[8:8 + size], rest[8 + size:]
            assert data[:1] == b"\n"
            data = data[1:]
        fields[key.decode()] = value.decode()
    return fields


@pytest.fixture
def journal() -> Iterator[tuple[socket.socket, str]]:
    """A stand-in for journald's socket (short path: AF_UNIX allows ~107)."""
    folder = tempfile.mkdtemp(prefix="j")
    path = os.path.join(folder, "socket")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(path)
    server.settimeout(5)
    yield server, path
    server.close()
    os.unlink(path)
    os.rmdir(folder)


def handler_for(path: str) -> JournalHandler:
    handler = JournalHandler(path)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


@pytest.mark.parametrize(("level", "prio"), [
    (logging.CRITICAL, "2"), (logging.ERROR, "3"), (logging.WARNING, "4"),
    (logging.INFO, "6"), (logging.DEBUG, "7"),
])
def test_journal_handler_sends_the_priority(
    journal: tuple[socket.socket, str], level: int, prio: str,
) -> None:
    server, path = journal
    handler_for(path).handle(record(level, "hello"))

    fields = parse_datagram(server.recv(65536))
    assert fields["MESSAGE"] == f"ibp-kiosk-launcher: {logging.getLevelName(level)} hello"
    assert fields["PRIORITY"] == prio
    assert fields["SYSLOG_IDENTIFIER"] == "ibp-kiosk"
    assert fields["CODE_FILE"] == __file__ and fields["CODE_LINE"] == "1"


def test_journal_handler_sends_a_traceback_as_one_entry(
    journal: tuple[socket.socket, str],
) -> None:
    server, path = journal
    handler_for(path).handle(record(logging.ERROR, "oops", exc=True))

    fields = parse_datagram(server.recv(65536))
    lines = fields["MESSAGE"].split("\n")
    assert lines[0] == "ibp-kiosk-launcher: ERROR oops"
    assert lines[1] == "Traceback (most recent call last):"
    assert lines[-1] == "ValueError: boom"
    assert fields["PRIORITY"] == "3"
    server.setblocking(False)
    with pytest.raises(BlockingIOError):
        server.recv(65536)  # nothing more: one entry


def test_journal_handler_falls_back_to_prefixed_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    with open(tmp_path / "err", "w+") as f:
        monkeypatch.setattr(sys, "stderr", f)
        handler_for(str(tmp_path / "no-socket")).handle(record(logging.ERROR, "oops", exc=True))
        f.seek(0)
        lines = f.read().splitlines()
    assert len(lines) > 2
    assert all(line.startswith("<3>") for line in lines)
    assert lines[-1] == "<3>ValueError: boom"


def test_fit_message_keeps_the_first_and_last_lines() -> None:
    text = "\n".join(["first", *(f"frame {i} " + "x" * 50 for i in range(200)), "ValueError: boom"])
    fitted = fit_message(text, limit=1000)
    assert len(fitted.encode()) <= 1000
    lines = fitted.split("\n")
    assert lines[0] == "first"
    assert lines[-1] == "ValueError: boom"
    assert lines[-2].startswith("frame 199 ")
    kept = len(lines) - 2
    assert lines[1] == f"[{201 - kept} lines left out]"
    assert fit_message("short") == "short"


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
