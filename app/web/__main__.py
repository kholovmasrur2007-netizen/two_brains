"""Entry point: ``python -m app.web``.

Starts uvicorn against ``app.web.server:app``. Defaults are sensible for
local use (127.0.0.1:8000); pass ``--host`` / ``--port`` to override.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="two_brains-web",
        description="Run the two_brains FastAPI server.",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000,
                        help="Listening port (default: 8000).")
    parser.add_argument("--reload", action="store_true",
                        help="Enable hot-reload (dev only).")
    args = parser.parse_args(argv)

    uvicorn.run(
        "app.web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
