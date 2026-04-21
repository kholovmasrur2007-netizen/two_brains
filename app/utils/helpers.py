"""Miscellaneous helpers.

Keep this module small; move functions out to dedicated files once they grow.
"""

from __future__ import annotations

import uuid


def new_id(prefix: str = "task") -> str:
    """Return a short, unique id suitable for Task/Plan identifiers."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
    # TODO: switch to ULID when ordering by creation-time matters.
