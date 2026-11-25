"""Read and check /etc/ibp-kiosk/station.toml (schema in CLAUDE.md)."""

from __future__ import annotations

import socket
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("/etc/ibp-kiosk/station.toml")
DEFAULT_INTERVAL = 15.0


class ConfigError(Exception):
    """station.toml is missing or invalid; the message says why."""


@dataclass(frozen=True)
class Tile:
    id: str
    label: str
    command: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class StatusCheck:
    label: str
    command: tuple[str, ...]
    interval: float = DEFAULT_INTERVAL


@dataclass(frozen=True)
class Config:
    name: str
    tiles: tuple[Tile, ...]
    statuses: tuple[StatusCheck, ...] = ()
    admin: tuple[Tile, ...] = ()
    autostart: str | None = None
    path: Path = field(default=DEFAULT_PATH)

    def tile(self, tile_id: str) -> Tile:
        return next(t for t in self.tiles if t.id == tile_id)


def load(path: Path) -> Config:
    """Read and check the file at path. Raises ConfigError."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"{path} does not exist.") from None
    except OSError as e:
        raise ConfigError(f"Cannot read {path}: {e.strerror}.") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}.") from None
    try:
        return parse(data, path)
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from None


def parse(data: dict[str, Any], path: Path = DEFAULT_PATH) -> Config:
    _keys(data, "the file", required=(), optional=("station", "tile", "status", "admin"))

    station = data.get("station", {})
    if not isinstance(station, dict):
        raise ConfigError("[station] must be a table.")
    _keys(station, "[station]", required=(), optional=("name", "autostart"))
    name = _str(station, "name", "[station]", required=False) or socket.gethostname()
    autostart = _str(station, "autostart", "[station]", required=False) or None

    tiles = _tiles(data, "tile")
    if not tiles:
        raise ConfigError("There are no [[tile]] entries.")
    admin = _tiles(data, "admin")
    if autostart is not None and autostart not in {t.id for t in tiles}:
        raise ConfigError(f'[station] autostart = "{autostart}" is not the id of a [[tile]].')

    statuses = []
    for i, entry in enumerate(_array(data, "status"), 1):
        where = f"[[status]] number {i}"
        _keys(entry, where, required=("label", "command"), optional=("interval",))
        interval = entry.get("interval", DEFAULT_INTERVAL)
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval < 1:
            raise ConfigError(f"{where}: interval must be a number of seconds, at least 1.")
        statuses.append(
            StatusCheck(
                label=_str(entry, "label", where),
                command=_command(entry, where),
                interval=float(interval),
            )
        )

    return Config(
        name=name,
        tiles=tiles,
        statuses=tuple(statuses),
        admin=admin,
        autostart=autostart,
        path=path,
    )


def _tiles(data: dict[str, Any], key: str) -> tuple[Tile, ...]:
    tiles: list[Tile] = []
    for i, entry in enumerate(_array(data, key), 1):
        where = f"[[{key}]] number {i}"
        _keys(entry, where, required=("id", "label", "command"), optional=("description",))
        tile = Tile(
            id=_str(entry, "id", where),
            label=_str(entry, "label", where),
            command=_command(entry, where),
            description=_str(entry, "description", where, required=False),
        )
        if any(t.id == tile.id for t in tiles):
            raise ConfigError(f'{where}: id "{tile.id}" is used twice.')
        tiles.append(tile)
    return tuple(tiles)


def _array(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ConfigError(f"{key} must be written as [[{key}]] tables.")
    return value


def _keys(table: dict[str, Any], where: str, required: tuple[str, ...], optional: tuple[str, ...]) -> None:
    for key in required:
        if key not in table:
            raise ConfigError(f"{where}: {key} is missing.")
    unknown = sorted(set(table) - set(required) - set(optional))
    if unknown:
        raise ConfigError(f"{where}: unknown key {', '.join(unknown)}.")


def _str(table: dict[str, Any], key: str, where: str, required: bool = True) -> str:
    value = table.get(key, "")
    if not isinstance(value, str):
        raise ConfigError(f"{where}: {key} must be a string.")
    value = value.strip()
    if required and not value:
        raise ConfigError(f"{where}: {key} must not be empty.")
    return value


def _command(table: dict[str, Any], where: str) -> tuple[str, ...]:
    value = table["command"]
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(a, str) for a in value)
        or not value[0]
    ):
        raise ConfigError(f'{where}: command must be a list of strings, like ["program", "arg"].')
    return tuple(value)
