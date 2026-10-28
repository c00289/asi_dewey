"""Read-only queries shared by the Dashboard screen and the ``status_report`` document.

Open Jira tickets, tasks ending soon, and the recent audit entries, in one place so the window
and a generated document show the same thing.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..brain import Brain

DUE_WINDOW_DAYS = 7


def open_jira_tickets(brain: Brain) -> list[dict[str, Any]]:
    return brain.service("jira_ticket").list({"status": "open"})


def tasks_due(brain: Brain, days: int = DUE_WINDOW_DAYS, today: dt.date | None = None) -> list[dict[str, Any]]:
    """Tasks whose end date falls between yesterday and ``today + days``, soonest first."""
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=days)
    tasks = brain.service("task").list(order_by="end")
    return [
        t for t in tasks
        if t.get("end") and today - dt.timedelta(days=1) <= dt.date.fromisoformat(t["end"]) <= horizon
    ]


def recent_changes(brain: Brain, limit: int = 25) -> list[dict[str, Any]]:
    return brain.storage.audit_tail(limit)
