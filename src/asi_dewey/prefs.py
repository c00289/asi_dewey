"""Per-person, per-machine preferences: one flat JSON object, today holding the latched theme.

A preference is not a project setting (``dewey.toml``) and not working knowledge (the
database): it lives in the user's state folder, in Dewey's own ``dewey`` subfolder so the
sibling tools never read each other's file. ``$ASI_DEWEY_PREFS`` overrides the path (the test
suite points it at a temporary file). Reads never fail: a missing or corrupt file is ``{}``.
Writes merge, go to a temporary file beside the target and ``os.replace`` it into place.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .version import __version__

ENV_PREFS = "ASI_DEWEY_PREFS"
TOOL = "asi_dewey"
_RELATIVE = ("asi", "dewey", "prefs.json")


def prefs_path() -> Path:
    """``$ASI_DEWEY_PREFS``, else ``%LOCALAPPDATA%\\asi\\dewey\\prefs.json``, else the XDG state folder."""
    override = os.environ.get(ENV_PREFS)
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]).joinpath(*_RELATIVE)
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]).joinpath(*_RELATIVE)
    return Path.home().joinpath(".local", "state", *_RELATIVE)


def read_prefs() -> dict[str, Any]:
    """The preferences as a dict; ``{}`` when the file is missing, unreadable, or not a JSON object."""
    try:
        data = json.loads(prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_prefs(**changes: Any) -> Path:
    """Merge ``changes`` into the file (creating folders as needed) and return its path."""
    path = prefs_path()
    merged = {
        **read_prefs(),
        **changes,
        "tool": TOOL,
        "version": __version__,
        "updated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".prefs-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
