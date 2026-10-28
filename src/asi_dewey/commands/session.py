"""The ``session`` verb: the automation session file, whether it is alive, whether it answers.

The one verb the CLI runs without opening a ``Brain``: it touches no database and must work
while a window holds the family lock. ``--quit`` asks the live window to close (``POST /quit``)
and waits up to five seconds for the file to go. The token is never printed: it is in the file
for anyone who can read the file, and a console or a log is not that.
"""

from __future__ import annotations

import os
import time
from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command

PUBLIC_KEYS = ("pid", "port", "address", "started_at", "db")
QUIT_WAIT = 5.0


def session_report(quit: bool = False) -> Result:
    """The ``Result`` of ``asi-dewey session [--quit]``; callable without a Brain."""
    from ..automation.server import current_server
    from ..automation.session import TOOL, SessionUnreachable, pid_alive, probe, read_raw_session, request, session_path

    path = session_path()
    raw = read_raw_session()
    present = raw is not None
    alive = bool(present and raw.get("tool") == TOOL and pid_alive(raw.get("pid")))
    own = current_server() if alive and raw.get("pid") == os.getpid() else None
    status: dict[str, Any] | None = None
    if own is not None:
        status = own.status_data()  # the window's own session: reported directly, no request to itself
    elif alive:
        status = probe(raw)
    data: dict[str, Any] = {
        "path": str(path),
        "present": present,
        "alive": alive,
        "reachable": status is not None,
        "session": {key: raw.get(key) for key in PUBLIC_KEYS} if present else None,
        "status": status,
        "quit": False,
    }
    if not quit:
        return Result.success(data)
    if status is None:
        return Result.failure("no live automation session to quit", data=data)
    if own is not None:
        own.quit()
    else:
        try:
            code, payload = request(raw, "POST", "/quit", timeout=QUIT_WAIT)
        except SessionUnreachable as exc:
            return Result.failure(str(exc), data=data)
        if code != 200 or not payload.get("ok"):
            errors = payload.get("errors") or [f"HTTP {code}"]
            return Result.failure(*[str(e) for e in errors], data=data)
        deadline = time.monotonic() + QUIT_WAIT
        while path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if path.exists():
            data["quit"] = True
            warning = "the window acknowledged the quit but the session file is still there"
            return Result.success(data, warnings=[warning])
    data["quit"] = True
    return Result.success(data)


@register_command
class SessionCommand(Command):
    verb = "session"
    help = "Report the automation session of a running window (--quit: ask it to close). Opens no database."
    arguments = (
        Argument(
            "quit", "POST /quit to the live session, then wait up to 5 s for its file to go", flag=True, type="bool"
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return session_report(quit=bool(args.get("quit")))
