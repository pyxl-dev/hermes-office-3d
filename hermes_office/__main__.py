"""``python -m hermes_office`` — start the office server."""

from __future__ import annotations

import argparse
import logging

from .config import Settings
from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="hermes-office-3d", description=__doc__)
    parser.add_argument("--host", default=None, help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="bind port (default 8765)")
    parser.add_argument("--demo", action="store_true", help="force synthetic demo fixtures")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings.from_env()
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    if args.demo:
        settings.hermes_api_key = ""  # forces demo_mode

    serve(settings)


if __name__ == "__main__":
    main()
