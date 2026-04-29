"""Per-user daily task quotas — second line of defence after rate limiting.

Rate limiting protects per-IP burst rates. Quotas protect against a user
running thousands of LLM tasks per day (which would burn a real budget).

Defaults (override via env):
    DAILY_TASK_QUOTA = 100           # tasks per user per day
    QUOTA_DISABLED   = false         # quotas off entirely

Quotas only apply when ``USE_DB=true``; without a DB there's nowhere to
store the counter, so we fall through to allow-all.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Final

from app.config import settings

DAILY_TASK_QUOTA: Final[int] = int(os.getenv("DAILY_TASK_QUOTA", "100"))
_DISABLED: Final[bool] = os.getenv("QUOTA_DISABLED", "false").lower() == "true"


class DailyQuotaExceeded(RuntimeError):
    """Raised when a user has exceeded their daily task budget."""


def check_and_record_quota(username: str | None) -> None:
    """Atomically increment today's counter and refuse if over the cap.

    Args:
        username: who's running the task. ``None`` means anonymous; with
            no DB or no auth we can't track them, so they get unlimited.

    Raises:
        DailyQuotaExceeded: when the user's counter would cross
        ``DAILY_TASK_QUOTA``. The current count is included in the message.
    """
    if _DISABLED or not username or not settings.use_db:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from app.db.engine import QuotaRow, get_session
    with get_session() as s:
        row = s.get(QuotaRow, (username, today))
        if row is None:
            s.add(QuotaRow(username=username, date_ymd=today, count="1"))
            s.commit()
            return
        current = int(row.count or "0")
        if current >= DAILY_TASK_QUOTA:
            raise DailyQuotaExceeded(
                f"daily task quota of {DAILY_TASK_QUOTA} reached "
                f"(used {current}); resets at midnight UTC"
            )
        row.count = str(current + 1)
        s.commit()


def usage_today(username: str) -> int:
    """Return the current counter for ``username`` (0 if no DB / no rows)."""
    if not settings.use_db:
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from app.db.engine import QuotaRow, get_session
    with get_session() as s:
        row = s.get(QuotaRow, (username, today))
        return int(row.count) if row else 0
