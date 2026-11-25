"""`python3 -m ibp_kiosk [--config PATH] [--windowed] [home]`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import DEFAULT_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ibp-kiosk-launcher",
        description="Full-screen launcher for IBP stations.",
    )
    parser.add_argument(
        "command", nargs="?", choices=["home"],
        help="home: close the running app and show the tiles in the running launcher",
    )
    parser.add_argument(
        "--config", type=Path,
        default=Path(os.environ.get("IBP_KIOSK_CONFIG") or DEFAULT_PATH),
        help=f"station.toml to read (default: $IBP_KIOSK_CONFIG or {DEFAULT_PATH})",
    )
    parser.add_argument(
        "--windowed", action="store_true",
        help="for development: a normal 1366x768 window that can be closed",
    )
    args = parser.parse_args(argv)

    if args.command == "home":
        from .ipc import send_home  # no Qt import: the Home key should be quick
        return send_home()

    from .app import run
    return run(args.config, windowed=args.windowed)


if __name__ == "__main__":
    sys.exit(main())
