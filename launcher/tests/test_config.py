from __future__ import annotations

import socket
from pathlib import Path

import pytest

from ibp_kiosk.config import ConfigError, load

from .conftest import LAUNCHER_DIR

MINIMAL = """
[[tile]]
id = "a"
label = "A"
command = ["true"]
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "station.toml"
    path.write_text(text)
    return path


def error(tmp_path: Path, text: str) -> str:
    with pytest.raises(ConfigError) as info:
        load(write(tmp_path, text))
    return str(info.value)


def test_example_loads() -> None:
    config = load(LAUNCHER_DIR / "examples" / "station.toml")
    assert config.name == "Dev station"
    assert config.tiles[0].id == "terminal"
    assert config.tiles[0].command == ("xterm",)
    assert config.statuses[0].label == "Network"
    assert [t.id for t in config.admin] == ["admin-terminal", "admin-fail"]


def test_contract_example_loads(tmp_path: Path) -> None:
    # The example from CLAUDE.md, with its autostart pointing at a tile it has.
    config = load(write(tmp_path, """
[station]
name = "Shipping 1"
autostart = "ship-individual"

[[tile]]
id = "ship-individual"
label = "Ship Individual"
description = "One package to one person"
command = ["ibp-kiosk-app", "ship-individual"]

[[status]]
label = "Label printer"
command = ["ibp-kiosk-status", "printer-shipping"]
interval = 15

[[admin]]
id = "wifi"
label = "Wi-Fi"
command = ["ibp-kiosk-app", "wifi"]
"""))
    assert config.autostart == "ship-individual"
    assert config.tiles[0].description == "One package to one person"
    assert config.statuses[0].interval == 15.0
    assert config.admin[0].command == ("ibp-kiosk-app", "wifi")


def test_defaults(tmp_path: Path) -> None:
    config = load(write(tmp_path, MINIMAL + '\n[[status]]\nlabel = "N"\ncommand = ["true"]\n'))
    assert config.name == socket.gethostname()
    assert config.autostart is None
    assert config.admin == ()
    assert config.tiles[0].description == ""
    assert config.statuses[0].interval == 15.0


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        load(tmp_path / "nope.toml")


def test_error_names_the_file(tmp_path: Path) -> None:
    assert error(tmp_path, "").startswith(f"{tmp_path / 'station.toml'}: ")


def test_bad_toml(tmp_path: Path) -> None:
    assert "not valid TOML" in error(tmp_path, "[[tile]\nid = ")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "no [[tile]]"),
        ('[station]\nname = "x"\n', "no [[tile]]"),
        (MINIMAL + "[[tiles]]\n", "unknown key tiles"),
        (MINIMAL.replace('label = "A"', 'label = "A"\ncolour = "red"'), "unknown key colour"),
        (MINIMAL.replace('label = "A"\n', ""), "label is missing"),
        (MINIMAL.replace('label = "A"', 'label = "  "'), "label must not be empty"),
        (MINIMAL.replace('label = "A"', "label = 3"), "label must be a string"),
        (MINIMAL.replace('["true"]', '"true"'), "command must be a list"),
        (MINIMAL.replace('["true"]', "[]"), "command must be a list"),
        (MINIMAL.replace('["true"]', '["true", 1]'), "command must be a list"),
        (MINIMAL + MINIMAL, 'id "a" is used twice'),
        ('[station]\nautostart = "b"\n' + MINIMAL, 'autostart = "b" is not the id'),
        ("station = 3\n" + MINIMAL, "[station] must be a table"),
        ("tile = 3\n", "[[tile]] tables"),
        (MINIMAL + '[[status]]\nlabel = "N"\ncommand = ["true"]\ninterval = 0\n', "interval"),
        (MINIMAL + '[[status]]\nlabel = "N"\ncommand = ["true"]\ninterval = "5"\n', "interval"),
        (MINIMAL + '[[status]]\nlabel = "N"\ncommand = ["true"]\ninterval = true\n', "interval"),
        (MINIMAL + '[[status]]\nlabel = "N"\n', "[[status]] number 1: command is missing"),
        (MINIMAL + '[[admin]]\nid = "w"\nlabel = "W"\n', "[[admin]] number 1: command"),
    ],
)
def test_invalid(tmp_path: Path, text: str, message: str) -> None:
    assert message in error(tmp_path, text)
