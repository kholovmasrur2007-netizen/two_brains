"""Project-wide logger backed by `rich` for readable CLI output."""

from __future__ import annotations

import logging

from rich.logging import RichHandler

from app.config import settings

_configured = False


def _configure() -> None:
    """Configure the root logger once per process."""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger; configures the root handler on first call."""
    _configure()
    return logging.getLogger(name)
