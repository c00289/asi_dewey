"""One primary tool at a time: the family lock shared by convention with asi_kletz.

The convention is written once, in the section "One primary tool at a time" of ``ASI_FUSA_TOOLS.md``,
and implemented twice, never shared as code. In short: a lock directory (``$ASI_PRIMARY_LOCK_DIR``,
else ``%LOCALAPPDATA%\\asi\\locks``, else the XDG state folder), a **family slot** ``primary.lock``
held while any primary tool runs, a **database slot** ``db-<sha1>.lock`` held while that database is
open, a non-blocking OS advisory lock on byte 0 of each file (released by the OS when the process
ends, so a crash never leaves a stale lock), and a best-effort ``.json`` beside each lock naming
the holder. Family slot first, then database slot. Refusal is ``PrimaryToolBusy``; ``wait`` polls
every 250 ms. There is no override.

``guard`` is the one ``PrimaryGuard`` per process: it reference-counts the slots across every open
``Brain``, so one process may hold several Brains (the test suite does) and the slot is released
when the last one closes.
"""

from __future__ import annotations

import datetime as dt
import errno
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .errors import PrimaryToolBusy
from .version import __version__

__all__ = [
    "ENV_LOCK_DIR",
    "FAMILY_STEM",
    "POLL_SECONDS",
    "TOOL",
    "PrimaryGuard",
    "PrimaryToolBusy",
    "SlotLock",
    "db_slot_name",
    "guard",
    "lock_dir",
]

ENV_LOCK_DIR = "ASI_PRIMARY_LOCK_DIR"
TOOL = "asi_dewey"
FAMILY_STEM = "primary"
POLL_SECONDS = 0.25
_RELATIVE = ("asi", "locks")
_BUSY_ERRNOS = {errno.EACCES, errno.EAGAIN, errno.EDEADLOCK, getattr(errno, "EWOULDBLOCK", errno.EAGAIN)}


def lock_dir() -> Path:
    """``$ASI_PRIMARY_LOCK_DIR``, else ``%LOCALAPPDATA%\\asi\\locks``, else the XDG state folder.

    Never inside a repo or a synced folder; the test suite points the variable at a temporary
    directory so the Dewey and Kletz suites can run at the same time.
    """
    override = os.environ.get(ENV_LOCK_DIR)
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]).joinpath(*_RELATIVE)
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]).joinpath(*_RELATIVE)
    return Path.home().joinpath(".local", "state", *_RELATIVE)


def resolve_db(db_path: str | os.PathLike[str]) -> str:
    """The absolute database path the slot name is derived from, lower-cased on Windows."""
    text = str(Path(db_path).resolve())
    return text.lower() if os.name == "nt" else text


def db_slot_name(db_path: str | os.PathLike[str]) -> str:
    """``db-<sha1>`` for the resolved absolute path (``resolve_db``)."""
    return "db-" + hashlib.sha1(resolve_db(db_path).encode("utf-8")).hexdigest()


def holder_info(db_path: str | None) -> dict[str, Any]:
    """What this process writes beside a lock it holds."""
    try:
        import getpass

        user = getpass.getuser()
    except Exception:  # no account name available: still informational
        user = None
    try:
        import socket

        host = socket.gethostname()
    except Exception:
        host = None
    return {
        "tool": TOOL,
        "version": __version__,
        "pid": os.getpid(),
        "started_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "db": db_path,
        "cwd": os.getcwd(),
        "host": host,
        "user": user,
    }


def _lock_byte(fd: int) -> None:
    """Take the non-blocking advisory lock on byte 0, or raise ``BlockingIOError``-like ``OSError``."""
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_byte(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def describe_holder(slot: str, holder: dict[str, Any] | None) -> str:
    """The one-line refusal message, e.g. ``asi_kletz is running (pid 4321, since ..., db ...)``."""
    if holder:
        tool = str(holder.get("tool") or "another primary tool")
        detail = [f"pid {holder.get('pid')}", f"since {holder.get('started_at')}"]
        if holder.get("db"):
            detail.append(f"db {holder['db']}")
        verb = "is running" if slot == "family" else "has the database open"
        who = f"{tool} {verb} ({', '.join(detail)})"
    else:
        who = "another primary tool is running (holder unknown)" if slot == "family" else (
            "another process has the database open (holder unknown)"
        )
    rule = "only one primary tool may run at a time" if slot == "family" else "a database is opened by one process"
    return f"{who}; {rule}. Close it, or retry with --wait."


class SlotLock:
    """One OS lock file plus its holder ``.json``, both in ``directory`` with the same ``stem``."""

    def __init__(self, directory: Path, stem: str) -> None:
        self.directory = Path(directory)
        self.stem = stem
        self.lock_path = self.directory / f"{stem}.lock"
        self.info_path = self.directory / f"{stem}.json"
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self, info: dict[str, Any], slot: str) -> None:
        """Take the lock or raise ``PrimaryToolBusy(slot, holder)``; writes ``info`` beside it."""
        if self._fd is not None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            try:
                if os.fstat(fd).st_size == 0:  # msvcrt wants at least one byte under the lock
                    os.write(fd, b"\0")
            except OSError:
                pass  # the byte is already locked by the holder: the lock attempt below says so
            try:
                _lock_byte(fd)
            except OSError as exc:
                if exc.errno in _BUSY_ERRNOS:
                    raise PrimaryToolBusy(slot, self.read_holder()) from None
                raise
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        self._write_info(info)

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            _unlock_byte(fd)
        except OSError:
            pass  # the OS drops the lock when the descriptor closes anyway
        finally:
            os.close(fd)

    def read_holder(self) -> dict[str, Any] | None:
        """The ``.json`` beside the lock as a dict, or ``None`` when missing or unreadable."""
        try:
            data = json.loads(self.info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _write_info(self, info: dict[str, Any]) -> None:
        tmp = self.info_path.with_name(f".{self.stem}-{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(tmp, self.info_path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass


class PrimaryGuard:
    """Process-wide, reference-counted ownership of the family slot and one database slot per path."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._family: dict[Path, tuple[SlotLock, int]] = {}  # per lock directory
        self._databases: dict[tuple[Path, str], tuple[SlotLock, int]] = {}

    @staticmethod
    def _db_key(db_path: str) -> str | None:
        return None if db_path == ":memory:" else db_slot_name(db_path)

    def acquire(self, db_path: str, wait: float = 0.0) -> None:
        """Hold the family slot and, unless ``db_path`` is ``:memory:``, the database slot.

        Polls every 250 ms for up to ``wait`` seconds, then raises ``PrimaryToolBusy``.
        """
        deadline = time.monotonic() + max(0.0, float(wait or 0.0))
        while True:
            try:
                with self._lock:
                    self._acquire_once(db_path)
                return
            except PrimaryToolBusy:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(POLL_SECONDS, remaining))

    def _acquire_once(self, db_path: str) -> None:
        directory = lock_dir()
        family, family_count = self._family.get(directory) or (SlotLock(directory, FAMILY_STEM), 0)
        if family_count == 0:
            family.acquire(holder_info(db_path), "family")
        stem = self._db_key(db_path)
        if stem is not None:
            key = (directory, stem)
            database, db_count = self._databases.get(key) or (SlotLock(directory, stem), 0)
            if db_count == 0:
                try:
                    database.acquire(holder_info(db_path), "database")
                except BaseException:
                    if family_count == 0:
                        family.release()
                    raise
            self._databases[key] = (database, db_count + 1)
        self._family[directory] = (family, family_count + 1)

    def release(self, db_path: str) -> None:
        """Undo one ``acquire``; the OS locks go when the last Brain on them closes."""
        with self._lock:
            directory = lock_dir()
            stem = self._db_key(db_path)
            if stem is not None:
                key = (directory, stem)
                database, db_count = self._databases.get(key) or (None, 0)
                if database is not None:
                    if db_count <= 1:
                        database.release()
                        del self._databases[key]
                    else:
                        self._databases[key] = (database, db_count - 1)
            family, family_count = self._family.get(directory) or (None, 0)
            if family is not None:
                if family_count <= 1:
                    family.release()
                    del self._family[directory]
                else:
                    self._family[directory] = (family, family_count - 1)

    def describe(self, db_path: str | None = None) -> dict[str, Any]:
        """For ``Brain.status()``: the holders written beside the family slot and ``db_path``'s slot."""
        with self._lock:
            directory = lock_dir()
            family = self._family.get(directory)
            out: dict[str, Any] = {
                "family": (family[0] if family else SlotLock(directory, FAMILY_STEM)).read_holder(),
                "database": None,
            }
            stem = self._db_key(db_path) if db_path else None
            if stem is not None:
                database = self._databases.get((directory, stem))
                out["database"] = (database[0] if database else SlotLock(directory, stem)).read_holder()
            return out


guard = PrimaryGuard()
