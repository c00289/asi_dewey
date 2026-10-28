"""The automation session file: how a CLI process finds the server of a running window.

One flat JSON object, ``%LOCALAPPDATA%\\asi\\dewey\\session.json`` beside ``prefs.json`` (the XDG
state folder elsewhere; ``$ASI_DEWEY_SESSION`` overrides the full path, the test suite points it at
a temporary file): ``tool``, ``version``, ``pid``, ``started_at``, ``host``, ``port``, ``address``,
``token`` and ``db``. The window writes it once its server has bound and removes it in ``close()``.
Every reader ignores a file whose ``pid`` is not alive, so a file left by a crash is harmless and is
overwritten by the next window. ``probe`` is the liveness check readers use before trusting the
file: ``GET /status`` must answer and name the same pid. ``forward`` is what the CLI does with a
command once the family lock has refused it in favour of a window of this tool.

The convention is shared by name with asi_kletz (``ASI_FUSA_TOOLS.md``, "The automation session")
and implemented twice, never shared as code.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..commands import Result
from ..prefs import prefs_path
from ..version import __version__

__all__ = [
    "ENV_AUTOMATION",
    "ENV_SESSION",
    "TOOL",
    "SessionUnreachable",
    "automation_enabled",
    "clear_session",
    "forward",
    "pid_alive",
    "probe",
    "read_raw_session",
    "read_session",
    "request",
    "session_path",
    "write_session",
]

ENV_SESSION = "ASI_DEWEY_SESSION"
ENV_AUTOMATION = "ASI_DEWEY_AUTOMATION"
TOOL = "asi_dewey"
FILE_NAME = "session.json"
DEFAULT_HOST = "127.0.0.1"
PROBE_TIMEOUT = 1.0
FORWARD_TIMEOUT = 60.0

_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class SessionUnreachable(OSError):
    """The session's server did not answer (connection refused, timeout, no HTTP at the port)."""


def automation_enabled() -> bool:
    """``ASI_DEWEY_AUTOMATION`` is not ``off`` (any other value, or unset, means on)."""
    return os.environ.get(ENV_AUTOMATION, "").strip().lower() != "off"


def session_path() -> Path:
    """``$ASI_DEWEY_SESSION``, else ``session.json`` beside ``prefs.json`` (see ``prefs.prefs_path``)."""
    override = os.environ.get(ENV_SESSION)
    if override:
        return Path(override)
    return prefs_path().with_name(FILE_NAME)


def write_session(port: int, token: str, db: str, started_at: str, host: str = DEFAULT_HOST) -> Path:
    """Write the file for this process (atomically; ``0o600`` on POSIX) and return its path."""
    path = session_path()
    data = {
        "tool": TOOL,
        "version": __version__,
        "pid": os.getpid(),
        "started_at": started_at,
        "host": host,
        "port": int(port),
        "address": f"http://{host}:{int(port)}",
        "token": token,
        "db": db,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".session-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def read_raw_session() -> dict[str, Any] | None:
    """The file as a dict, dead pid or not; ``None`` when missing, unreadable, or not a JSON object."""
    try:
        data = json.loads(session_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_session() -> dict[str, Any] | None:
    """The session of a live window of this tool, or ``None``.

    ``None`` when the file is missing or corrupt, names another tool, has no token or port, or
    names a pid that is not alive.
    """
    data = read_raw_session()
    if not data or data.get("tool") != TOOL:
        return None
    pid, token, port = data.get("pid"), data.get("token"), data.get("port")
    if not isinstance(pid, int) or not isinstance(port, int) or not token or not isinstance(token, str):
        return None
    if not pid_alive(pid):
        return None
    data.setdefault("host", DEFAULT_HOST)
    data.setdefault("address", f"http://{data['host']}:{port}")
    return data


def clear_session(pid: int | None = None) -> None:
    """Remove the file, but only when it names ``pid`` (this process by default)."""
    pid = os.getpid() if pid is None else pid
    data = read_raw_session()
    if data is None or data.get("pid") != pid:
        return
    try:
        session_path().unlink()
    except OSError:
        pass


def pid_alive(pid: Any) -> bool:
    """Whether a process with ``pid`` is running (``OpenProcess`` on Windows, ``kill 0`` elsewhere)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED  # exists, but belongs to someone else
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# -- the client side ----------------------------------------------------------------------------
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback: never through a proxy


def request(
    session: dict[str, Any], method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 5.0
) -> tuple[int, dict[str, Any]]:
    """One HTTP call to the session's server; ``(status, json)``. Raises ``SessionUnreachable``."""
    url = str(session["address"]).rstrip("/") + path
    data = None if body is None else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Authorization": f"Bearer {session.get('token', '')}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _opener.open(req, timeout=timeout) as response:
            return int(response.status), _payload(response.read())
    except urllib.error.HTTPError as exc:
        return int(exc.code), _payload(exc.read())
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SessionUnreachable(f"the automation session at {session['address']} did not answer") from exc


def _payload(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def probe(session: dict[str, Any], timeout: float = PROBE_TIMEOUT) -> dict[str, Any] | None:
    """``GET /status``; its ``data`` when it answers and names the file's pid, else ``None``."""
    try:
        status, payload = request(session, "GET", "/status", timeout=timeout)
    except SessionUnreachable:
        return None
    data = payload.get("data")
    if status != 200 or not payload.get("ok") or not isinstance(data, dict):
        return None
    if data.get("pid") != session.get("pid"):
        return None
    return data


def forward(
    session: dict[str, Any], verb: str, args: dict[str, Any] | None, actor: str, timeout: float = FORWARD_TIMEOUT
) -> Result:
    """``POST /execute`` and return the command's ``Result`` as the window produced it.

    Raises ``SessionUnreachable`` when the transport fails or the answer is not a ``Result``: the
    command did not run, which is never exit 1.
    """
    status, payload = request(
        session, "POST", "/execute", {"verb": verb, "args": dict(args or {}), "actor": actor}, timeout=timeout
    )
    if status != 200 or "ok" not in payload:
        detail = "; ".join(str(e) for e in payload.get("errors") or ()) or f"HTTP {status}"
        raise SessionUnreachable(f"the automation session at {session['address']} did not answer: {detail}")
    return Result(
        ok=bool(payload.get("ok")),
        data=payload.get("data"),
        errors=[str(e) for e in payload.get("errors") or ()],
        warnings=[str(w) for w in payload.get("warnings") or ()],
        verb=payload.get("verb"),
    )
