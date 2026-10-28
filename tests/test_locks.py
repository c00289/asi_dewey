"""One primary tool at a time: the family lock (``asi_dewey.locks``)."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

from asi_dewey import Brain, PrimaryToolBusy
from asi_dewey.locks import ENV_LOCK_DIR, SlotLock, db_slot_name, lock_dir, resolve_db
from tests.conftest import HOLD_BRAIN, HOLD_SIBLING


def _slot_free(directory: Path, stem: str = "primary") -> bool:
    """Try the OS lock from this process once; True when nobody holds it."""
    probe = SlotLock(directory, stem)
    try:
        probe.acquire({"tool": "probe"}, "family")
    except PrimaryToolBusy:
        return False
    probe.release()
    return True


def test_lock_dir_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_LOCK_DIR, str(tmp_path / "custom"))
    assert lock_dir() == tmp_path / "custom"
    monkeypatch.delenv(ENV_LOCK_DIR)
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
        assert lock_dir() == tmp_path / "local" / "asi" / "locks"
        monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert lock_dir() == tmp_path / "xdg" / "asi" / "locks"
    monkeypatch.delenv("XDG_STATE_HOME")
    assert lock_dir() == Path.home() / ".local" / "state" / "asi" / "locks"


def test_db_slot_name_is_sha1_of_the_resolved_path(tmp_path):
    db = tmp_path / "Mixed Case.db"
    resolved = str(db.resolve())
    if os.name == "nt":
        resolved = resolved.lower()
    assert resolve_db(db) == resolved
    assert db_slot_name(db) == "db-" + hashlib.sha1(resolved.encode("utf-8")).hexdigest()
    assert db_slot_name(str(db)) == db_slot_name(tmp_path / "sub" / ".." / "Mixed Case.db")


def test_same_process_many_brains_hold_the_family_slot_once(seeded, tmp_path):
    directory = lock_dir()
    assert not _slot_free(directory)
    other = Brain(tmp_path / "other.db")
    memory = Brain(":memory:")
    names = {p.name for p in directory.iterdir()}
    assert "primary.lock" in names and "primary.json" in names
    assert db_slot_name(seeded.db_path) + ".lock" in names and db_slot_name(other.db_path) + ".lock" in names
    assert len([n for n in names if n.startswith("db-") and n.endswith(".lock")]) == 2  # :memory: takes none
    other.close()
    assert not _slot_free(directory)
    assert _slot_free(directory, db_slot_name(other.db_path))
    memory.close()
    memory.close()  # idempotent
    assert not _slot_free(directory)  # seeded still open
    seeded.close()
    assert _slot_free(directory)


def test_status_reports_lock_dir_and_holders(brain):
    status = brain.status()
    assert status["lock_dir"] == str(lock_dir())
    family, database = status["locks"]["family"], status["locks"]["database"]
    assert family["pid"] == os.getpid() and family["tool"] == "asi_dewey"
    assert database["pid"] == os.getpid() and database["db"] == brain.db_path
    for key in ("tool", "version", "pid", "started_at", "db", "cwd", "host", "user"):
        assert key in family


def test_memory_database_takes_only_the_family_slot():
    with Brain(":memory:") as brain:
        names = {p.name for p in lock_dir().iterdir()}
        assert names == {"primary.lock", "primary.json"}
        locks = brain.status()["locks"]
        assert locks["family"]["pid"] == os.getpid() and locks["database"] is None


def test_second_process_of_the_same_tool_is_refused(hold, tmp_path):
    holder = hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0")
    with pytest.raises(PrimaryToolBusy) as info:
        Brain(tmp_path / "other.db")
    assert info.value.slot == "family"
    assert info.value.holder["tool"] == "asi_dewey" and info.value.holder["pid"] == holder.pid
    assert "asi_dewey is running (pid" in str(info.value) and "--wait" in str(info.value)
    with pytest.raises(PrimaryToolBusy) as same:
        Brain(tmp_path / "held.db")
    assert same.value.slot == "family"  # the family slot is checked first
    assert not (tmp_path / "other.db").exists()  # a refused process never opens the SQLite file
    holder.release()
    with Brain(tmp_path / "held.db") as brain:
        assert brain.status()["locks"]["family"]["pid"] == os.getpid()


def test_simulated_sibling_is_refused_by_the_convention(hold, tmp_path):
    holder = hold(HOLD_SIBLING, str(lock_dir()), "0")
    with pytest.raises(PrimaryToolBusy) as info:
        Brain(tmp_path / "dewey.db")
    assert info.value.slot == "family"
    assert info.value.holder["tool"] == "asi_kletz" and info.value.holder["pid"] == holder.pid
    assert str(info.value).startswith("asi_kletz is running (pid ")
    holder.release()
    with Brain(tmp_path / "dewey.db"):
        pass


def test_crash_releases_the_slot(hold, tmp_path):
    holder = hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0")
    with pytest.raises(PrimaryToolBusy):
        Brain(tmp_path / "held.db")
    holder.kill()
    started = time.monotonic()
    # the OS drops the lock with the process; a short wait covers the kernel's teardown latency on Windows
    with Brain(tmp_path / "held.db", wait=5) as brain:
        assert brain.status()["locks"]["family"]["pid"] == os.getpid()
    assert time.monotonic() - started < 5  # no stale lock: it came free at once, not at the deadline


def test_wait_polls_until_the_holder_exits(hold, tmp_path):
    hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0.5")
    started = time.monotonic()
    with Brain(tmp_path / "held.db", wait=10) as brain:
        assert brain.status()["locks"]["family"]["pid"] == os.getpid()
    assert time.monotonic() - started < 10


def test_wait_gives_up_after_the_time_is_up(hold, tmp_path):
    hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0")
    started = time.monotonic()
    with pytest.raises(PrimaryToolBusy):
        Brain(tmp_path / "other.db", wait=0.3)
    assert 0.25 <= time.monotonic() - started < 5


def test_database_slot_refusal_releases_the_family_slot(tmp_path):
    """A foreign holder of the database slot alone: the family slot is taken, then given back."""
    directory = lock_dir()
    stem = db_slot_name(tmp_path / "x.db")
    foreign = SlotLock(directory, stem)
    foreign.acquire({"tool": "probe", "pid": 1, "started_at": "now", "db": "x"}, "database")
    try:
        with pytest.raises(PrimaryToolBusy) as info:
            Brain(tmp_path / "x.db")
        assert info.value.slot == "database" and "has the database open" in str(info.value)
        assert _slot_free(directory)
    finally:
        foreign.release()
    with Brain(tmp_path / "x.db"):
        pass
