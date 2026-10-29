from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from asi_dewey import Brain
from asi_dewey.automation.session import ENV_AUTOMATION, ENV_SESSION
from asi_dewey.brain import (
    ENV_CONFIG,
    ENV_CONTROL_STRUCTURES,
    ENV_DB,
    ENV_EVIDENCE,
    ENV_OUT,
    ENV_WORKBOOK,
    load_config,
)
from asi_dewey.gui.theme import ENV_THEME
from asi_dewey.locks import ENV_LOCK_DIR
from asi_dewey.prefs import ENV_PREFS

REPO_ROOT = Path(__file__).resolve().parent.parent
# the real workbook, if dewey.toml in the repo names one; the seeding test skips otherwise
WORKBOOK = Path(load_config(REPO_ROOT / "dewey.toml").get("workbook") or REPO_ROOT / "dewey.xlsx")


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, tmp_path):
    """Tests never see the developer's dewey.toml or environment: no test may touch a real workbook."""
    monkeypatch.setenv(ENV_CONFIG, str(tmp_path / "absent.toml"))
    monkeypatch.delenv(ENV_DB, raising=False)
    monkeypatch.delenv(ENV_WORKBOOK, raising=False)
    monkeypatch.delenv(ENV_OUT, raising=False)
    monkeypatch.delenv(ENV_EVIDENCE, raising=False)
    # the template builder never finds the private shelf beside the repo by accident: a test that
    # wants it (the local-only smoke test) points the variable at it on purpose
    monkeypatch.setenv(ENV_CONTROL_STRUCTURES, str(tmp_path / "no-control-structures"))
    # no test reads or writes the developer's latched theme, and none inherits a theme override
    monkeypatch.setenv(ENV_PREFS, str(tmp_path / "prefs.json"))
    monkeypatch.delenv(ENV_THEME, raising=False)
    # no test reads or writes the real automation session file, and a developer's open window
    # never receives test traffic; the server is on (test windows bind 127.0.0.1 on port 0)
    monkeypatch.setenv(ENV_SESSION, str(tmp_path / "session.json"))
    monkeypatch.delenv(ENV_AUTOMATION, raising=False)
    # no test reaches Jira: asi_hopper replays fixtures (test_jira.py points it at the recorded ones;
    # everywhere else the directory is empty, so a stray `jira live` is a failed Result, never a call)
    monkeypatch.delenv("ASI_HOPPER_CONFIG", raising=False)
    monkeypatch.setenv("ASI_HOPPER_GATEWAY", "replay")
    monkeypatch.setenv("ASI_HOPPER_FIXTURES", str(tmp_path / "no-fixtures"))
    # the family lock lives in a per-test directory: the suite never touches the real lock
    # directory, and the Dewey and Kletz suites can run at the same time
    monkeypatch.setenv(ENV_LOCK_DIR, str(tmp_path / "locks"))


@pytest.fixture
def brain(tmp_path):
    with Brain(tmp_path / "test.db", workbook_path=tmp_path / "view.xlsx") as b:
        yield b


@pytest.fixture
def seeded(brain):
    brain.execute("create", entity="fact", data={"order": 1, "name": "Project code", "text": "PRJ-0001"})
    brain.execute("create", entity="fact", data={"order": 2, "name": "Product", "text": "Wheel Loader"})
    brain.execute("create", entity="task", data={
        "order": 1, "task_class": "administrative", "name": "Stand-up", "start": "2026-10-20", "end": 46318,
    })
    brain.execute("create", entity="link", data={"order": 1, "link_class": "tool", "name": "JIRA", "url": "https://x.y/z"})
    brain.execute("create", entity="safety_plan_row", data={
        "order": 1, "pdp_phase": "1", "lifecycle_phase": "1. Concept Development",
        "deliverable": "Safety Plan", "loc_dms": 1, "ref_qf_17": "1", "author_fusa_engineer": True,
        "verify_level_u3_refer_section_3_2": 1, "reviewer_tech_lead_functional_safety": 1,
    })
    return brain


# -- the family lock: holder processes ------------------------------------------------------------
# A holder is a second process that takes the slot, prints "ready", and keeps it until its stdin
# closes (or for a fixed number of seconds). It inherits the per-test lock directory. The holder
# prints its own pid: on Windows a venv's python.exe is a launcher whose child is the interpreter,
# so ``Popen.pid`` is not the pid the lock holder writes.

HOLD_BRAIN = """
import os, sys, time
from asi_dewey import Brain
db, seconds = sys.argv[1], float(sys.argv[2])
b = Brain(db)
print("ready", os.getpid(), flush=True)
if seconds > 0:
    time.sleep(seconds)
else:
    sys.stdin.readline()
b.close()
print("released", flush=True)
"""

# the simulated sibling: no asi_dewey import, the convention taken with raw msvcrt / fcntl
HOLD_SIBLING = """
import datetime, json, os, sys, time
directory, seconds = sys.argv[1], float(sys.argv[2])
os.makedirs(directory, exist_ok=True)
fd = os.open(os.path.join(directory, "primary.lock"), os.O_RDWR | os.O_CREAT, 0o644)
if os.fstat(fd).st_size == 0:
    os.write(fd, bytes([0]))
os.lseek(fd, 0, os.SEEK_SET)
if os.name == "nt":
    import msvcrt
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
with open(os.path.join(directory, "primary.json"), "w", encoding="utf-8") as handle:
    json.dump({
        "tool": "asi_kletz", "version": "0.6.0", "pid": os.getpid(),
        "started_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat(),
        "db": "C:/elsewhere/kletz.db", "cwd": os.getcwd(), "host": "sibling-host", "user": "sibling",
    }, handle)
print("ready", os.getpid(), flush=True)
if seconds > 0:
    time.sleep(seconds)
else:
    sys.stdin.readline()
"""


class Holder:
    """A subprocess holding a slot. ``release()`` lets it finish; ``kill()`` simulates a crash."""

    def __init__(self, script: str, *args: str) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-c", script, *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=dict(os.environ),
        )
        line = self.proc.stdout.readline().strip()
        words = line.split()
        if not words or words[0] != "ready":
            self.proc.kill()  # kill first: reading stderr of a live child waiting on stdin never returns
            err = self.proc.stderr.read()
            raise RuntimeError(f"holder did not start: {line!r}\n{err}")
        self._pid = int(words[1]) if len(words) > 1 else self.proc.pid

    @property
    def pid(self) -> int:
        return self._pid  # the pid the holder reported, the one it writes into the holder json

    def release(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write("\n")
                self.proc.stdin.close()
            except OSError:
                pass
            self.proc.wait(timeout=20)

    def kill(self) -> None:
        """Terminate the interpreter itself (not only a launcher in front of it), like a crash."""
        if self.proc.poll() is None:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except OSError:
                pass
            self.proc.kill()
            self.proc.wait(timeout=20)


@pytest.fixture
def hold():
    """``hold(script, *args)`` starts a holder and guarantees it is gone when the test ends."""
    holders: list[Holder] = []

    def start(script: str, *args: str) -> Holder:
        holder = Holder(script, *args)
        holders.append(holder)
        return holder

    yield start
    for holder in holders:
        holder.kill()
