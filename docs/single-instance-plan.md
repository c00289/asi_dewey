# ASI Dewey — Plan: one primary tool at a time (the family lock)

**Status:** Implemented 2026-10-27 (asi_dewey 0.6.0); deviations recorded in the CHANGELOG entry
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_dewey 0.6.0
**Re-targeted:** 2026-10-27, from 0.3.0, because 0.3.0 shipped the theme palette; 0.4.0 and 0.5.0 are window work (see the family version table).
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md), section "One primary tool at a time"
**Sister plan:** [asi_kletz/docs/single-instance-plan.md](../../asi_kletz/docs/single-instance-plan.md).
Same convention, implemented twice, never shared as code.

---

## 1. The rule

Two rules, decided by the owner on 2026-10-27, enforced in code:

1. **At most one primary tool runs at a time.** While any process of asi_dewey or asi_kletz is
   alive, no other process of either tool may start. Zero or one, never two.
2. **The same tool never runs twice.** Rule 1 already implies it; rule 2 is stated and enforced
   separately so that it survives any future loosening of rule 1 and so that a misconfigured
   family lock still protects the database.

"Runs" means **holds an open `Brain`**. The CLI holds one for the milliseconds a command takes,
the window holds one for the session, a Python caller holds one between `Brain(...)` and
`close()`. The rule is about processes: one process may open as many `Brain` objects as it
likes (the test suite does), and the slot is released when the last one closes.

What this gives the family: exactly one writer on every SQLite database at any moment, a
definite answer to "who has the database open", and no way for two front ends to interleave
edits without the event bus seeing them. What it does **not** give: it does not stop OneDrive
from touching files, and it does not reach across machines or user accounts.

Consequences, stated plainly because they change today's habits:

- `asi-dewey list` while the Dewey window is open is **refused** with exit code 3. Before this
  plan it worked at the SQLite level but the window did not refresh; since 0.7.0 the local
  automation server (`automation-server-plan.md`) is the way an agent drives a running window,
  and the CLI forwards a refused command to it.
- `asi-kletz …` while the Dewey window is open is refused the same way, and vice versa.
- Moving data between Dewey and Kletz is done **sequentially through files** (`dump` in one,
  `load` in the other), never by holding both open. This is the share-nothing rule with teeth.
- Scripts that call both tools gain `--wait <seconds>` to queue for the slot instead of failing.

## 2. What exists today (verified 2026-10-27)

| Fact | Where |
|---|---|
| `Brain.__init__` opens storage; `Brain.close()` closes it; `__enter__`/`__exit__` wrap them. | `brain.py` |
| The CLI does `with Brain(ns.db) as brain:` around one command and returns 0 or 1. | `automation/cli.py` |
| The window does `with Brain(ns.db) as brain: launch(brain, …)`. | `gui/app.py` |
| Every deliberate error derives from `BrainError`; the dispatcher turns them into `Result.failure`. | `errors.py`, `commands/dispatcher.py` |
| Tests open several `Brain`s in one process at once (`seeded` plus `Brain(tmp_path / "other.db")`), and `Brain(":memory:")`. | `tests/test_transfer.py`, `tests/test_generate.py` |
| Tests are isolated from the developer's config and environment by an autouse fixture. | `tests/conftest.py` |
| `.gitignore` ignores `*.db`, `*.db-journal`, `*.xlsx`, `out/`. | `.gitignore` |

Nothing in Dewey knows that Kletz exists, and that stays true. The two implementations agree
through the convention in [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md), not through an import.

## 3. Design

### 3.1 The convention (copied verbatim from ASI_FUSA_TOOLS.md; that file is the authority)

- **Lock directory**: `$ASI_PRIMARY_LOCK_DIR` if set; else `%LOCALAPPDATA%\asi\locks` on Windows;
  else `$XDG_STATE_HOME/asi/locks`; else `~/.local/state/asi/locks`. Created on demand. Never
  inside a repo, never inside OneDrive.
- **Family slot**: file `primary.lock`. Holding it means "a primary tool is running".
- **Database slot**: file `db-<sha1>.lock`, where `<sha1>` is the SHA-1 hex digest of the
  resolved absolute database path, lower-cased on Windows. Holding it means "this database is
  open". `:memory:` databases take no database slot.
- **Locking primitive**: an OS advisory lock on byte 0 of the file, non-blocking:
  `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` on Windows (the file is kept at least one byte long),
  `fcntl.flock(fd, LOCK_EX | LOCK_NB)` elsewhere. The OS releases it when the process ends, so
  a crash never leaves a stale lock.
- **Holder information**: beside each `.lock`, a `.json` with the same stem
  (`primary.json`, `db-<sha1>.json`) written best-effort by the holder after it acquires:
  `{"tool", "version", "pid", "started_at" (UTC ISO 8601), "db", "cwd", "host", "user"}`.
  It is informational; the lock is the truth. It is a separate file so a refused process can
  read it while the lock is held.
- **Order**: family slot first, then database slot. If the database slot fails, the family
  slot is released before reporting.
- **Refusal**: exit code **3** from a CLI, a JSON `Result` with `ok: false` on stdout whose
  `errors[0]` names the holder, and `data = {"slot": "family" | "database", "holder": {...} | null}`.
- **Waiting**: `--wait <seconds>` on every CLI and GUI entry point polls every 250 ms until the
  slot is free or the time is up, then refuses with exit code 3.
- **No override flag.** The only way around the rule is pointing `ASI_PRIMARY_LOCK_DIR` at a
  private directory, which is what test suites do. `ASI_PRIMARY_LOCK_DIR` is the one environment
  variable the primary tools deliberately share; it is a convention, not code.

### 3.2 New module: `asi_dewey/locks.py`

```python
class PrimaryToolBusy(BrainError):
    slot: str                 # "family" | "database"
    holder: dict | None       # parsed .json, or None if unreadable

def lock_dir() -> Path
def db_slot_name(db_path: str) -> str          # "db-<sha1>"
class SlotLock:                                # one OS lock + its info file
    def __init__(self, directory: Path, stem: str)
    def acquire(self, info: dict) -> None      # raises PrimaryToolBusy
    def release(self) -> None
    def read_holder(self) -> dict | None
class PrimaryGuard:                            # process-wide, reference counted
    def acquire(self, db_path: str, wait: float = 0.0) -> None
    def release(self, db_path: str) -> None
    def describe(self) -> dict                 # for status()
guard = PrimaryGuard()                         # the one instance per process
```

`PrimaryGuard` keeps one family `SlotLock` with a reference count across every open `Brain` in
the process, and one database `SlotLock` per resolved path with its own count. First `Brain`
acquires, last `close()` releases. The guard is thread-safe (a `threading.Lock`) because the
window may build documents in a thread later.

### 3.3 Brain

- `Brain.__init__(…, wait: float = 0.0)` calls `guard.acquire(self.db_path, wait)` **before**
  `StorageFactory.create`, so a refused process never opens the SQLite file at all.
- `Brain.close()` closes storage, then `guard.release(self.db_path)`. `close()` is idempotent.
- `Brain.status()` gains `"lock_dir"` and `"locks": {"family": {...holder...}, "database": {...}}`.
- `brain.py` exports `PrimaryToolBusy` through `asi_dewey.__init__` for Python callers.

### 3.4 CLI

- Global flag `--wait SECONDS` (default 0) on `asi-dewey` and `asi-dewey-gui`.
- `main()` wraps `Brain(ns.db, wait=ns.wait)` in `try/except PrimaryToolBusy`; on refusal it
  prints `Result.failure(str(exc), data={"slot": exc.slot, "holder": exc.holder}, verb=ns.verb)`
  as JSON and returns **3**. Exit code 1 keeps meaning "the command ran and failed".
- The message reads, for example:
  `asi_kletz is running (pid 4321, since 2026-10-27T17:02:11Z, db C:\…\kletz.db); only one primary tool may run at a time. Close it, or retry with --wait.`

### 3.5 Window

- `gui/app.py` catches `PrimaryToolBusy` and shows a dialog with the holder line and two
  buttons, **Retry** and **Quit**; Retry re-attempts once. With `interactive=False` (tests) it
  returns 3 without a dialog.
- The About box shows the lock directory.

### 3.6 Scripts and agents

- A `.jsonl` script runs inside one `Brain`, so it is one instance; nothing changes.
- An agent that drives Dewey and Kletz runs them **one after the other**, with `--wait` when it
  cannot know whether the window is open. The README says this in the "Agents" paragraph.
- `execute_dict` payloads are unchanged; the refusal happens before any command exists.

### 3.7 Configuration and ignore files

- No new key in `dewey.toml`: the lock directory is a family-wide environment variable, not a
  per-tool setting, so that both tools always agree on it.
- `dewey.example.toml` gets a comment pointing at `ASI_PRIMARY_LOCK_DIR`.
- `.gitignore` gains `*.lock` and `*.lock.json` as a precaution; by convention no lock file is
  ever created inside a repo.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Locks | `locks.py` with `SlotLock`, `PrimaryGuard`, `PrimaryToolBusy`; `Brain` acquires and releases; `status()` reports; `conftest.py` sets `ASI_PRIMARY_LOCK_DIR` to a per-test directory. | Existing suite still passes unchanged; the two-process refusal test passes. |
| 2. Front ends | `--wait` on CLI and GUI; exit code 3; busy dialog; About box. | CLI and GUI refusal tests pass; manual check: open the window, run `asi-dewey status`, get exit 3 and the holder line. |
| 3. Interop | The simulated-sibling test (a subprocess that takes `primary.lock` with raw `msvcrt`/`fcntl` and writes a `primary.json` saying `"tool": "asi_kletz"`) and the crash-release test. | Both pass on Windows; the POSIX branch is covered by the same tests when run there. |
| 4. Release | README section "One at a time", CHANGELOG `0.6.0`, `version.py` and `pyproject.toml` 0.6.0, `plan.md` sections 7.3 and 10, `dewey.example.toml` comment, `.gitignore`; automation server promoted to first in "Planned". | `uv run pytest` and `uv run ruff check src tests` clean; tag left to the owner. |

## 5. Files touched

```
pyproject.toml, src/asi_dewey/version.py   0.3.0
src/asi_dewey/locks.py                     new
src/asi_dewey/errors.py                    PrimaryToolBusy (or defined in locks.py and re-exported here)
src/asi_dewey/brain.py                     wait=, acquire before storage, release in close, status()
src/asi_dewey/__init__.py                  export PrimaryToolBusy
src/asi_dewey/automation/cli.py            --wait, exit 3
src/asi_dewey/gui/app.py                   --wait, busy dialog, exit 3
src/asi_dewey/gui/main_window.py           About box line
tests/conftest.py                          ASI_PRIMARY_LOCK_DIR -> tmp_path
tests/test_locks.py                        new
tests/test_cli.py, tests/test_gui.py       refusal cases
dewey.example.toml, .gitignore, README.md, CHANGELOG.md, docs/plan.md
```

No change to `schema/`, `storage/`, `repositories/`, `services/`, `commands/`, `io/`, or
`generate/`. Schema version stays 1.

## 6. Tests

- **Same process, many Brains**: `seeded` plus `Brain(tmp_path / "other.db")` plus
  `Brain(":memory:")` all open at once; the family slot is held once and released only after the
  last `close()` (checked by a second process that polls the lock).
- **Second process, same tool**: a subprocess running `python -c "from asi_dewey import Brain; …"`
  holds a `Brain` on a database and signals readiness; `Brain(other_db)` in the test process
  raises `PrimaryToolBusy` with `slot == "family"` and `holder["tool"] == "asi_dewey"`;
  `Brain(same_db)` raises with the same slot (family is checked first).
- **Simulated sibling**: a subprocess with no `asi_dewey` import takes `primary.lock` by the
  convention and writes `primary.json` with `"tool": "asi_kletz"`; `Brain(...)` raises with
  `holder["tool"] == "asi_kletz"`. This is the interoperability test; it checks the convention,
  not Kletz's code.
- **Crash release**: the holder subprocess is killed; `Brain(...)` then succeeds immediately.
- **Wait**: holder exits after 0.5 s; `Brain(db, wait=5)` succeeds; `Brain(db, wait=0.2)` raises.
- **CLI**: while a holder runs, `asi-dewey --db x status` exits 3 and prints a JSON `Result` with
  `ok: false`, `data.slot`, `data.holder.pid`; with `--wait 5` and a holder that exits, exit 0.
- **GUI**: `launch` path with `interactive=False` while a holder runs returns 3 and creates no window.
- **Status**: `status()["locks"]["family"]["pid"] == os.getpid()` while open.
- **Isolation**: the autouse fixture points `ASI_PRIMARY_LOCK_DIR` at `tmp_path`, so the suite
  never touches the real lock directory and the Dewey and Kletz suites can run at the same time.
- **Memory database**: `Brain(":memory:")` holds the family slot and no database slot.

## 7. Risks and decisions

| Risk | Decision |
|---|---|
| This does not fix uv or SQLite under OneDrive | Stated in section 1. The family lock is about ownership, not sync. Moving the repos or the databases out of the synced folder remains the fix for that. |
| Habit: CLI alongside the open window | Refused from 0.3.0. The local automation server becomes the next feature; until then, close the window or script the work. |
| Agents running both tools in parallel (as the 0.2.0 implementation agents did) | They serialise. Briefs say "use `--wait`". |
| Lock files under OneDrive would themselves be synced and fought over | They never are: the lock directory is under `%LOCALAPPDATA%`, which OneDrive does not sync. |
| Per-user, per-machine scope | Documented. Two Windows accounts, or two laptops sharing a database over OneDrive, are not covered; sharing a SQLite file over OneDrive is already unsupported. |
| `msvcrt.locking` details | Lock through a real `os.open` descriptor; unlock before closing; the file is padded to one byte; `OSError` with `EACCES`/`EDEADLOCK` means busy. |
| Thread safety | `PrimaryGuard` holds a `threading.Lock`; the window may build documents in a thread later. |
| A Python caller forgets `close()` | The slot stays held until the process exits, which is the rule working as intended; the README recommends the context manager, which already exists. |
| Kletz and Dewey drift in their implementations | The convention is written once in ASI_FUSA_TOOLS.md and both plans copy it verbatim; each suite has the simulated-sibling test. |

## 8. Open questions

None. The rule, the convention, the exit code, the wait flag, and the absence of an override
flag were decided on 2026-10-27.

## 9. Change log

- 2026-10-27 Draft 0.1: rule, verified starting point, convention, `locks.py`, Brain, CLI,
  window, scripts, phases, files, tests, risks.
