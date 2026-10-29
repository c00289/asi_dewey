# ASI Dewey

One of the [ASI FuSa tools](https://github.com/c00289/c00289/blob/main/README.md) by Roy Mendoza; the master README there lists every sibling.

A functional-safety (FuSa) working-knowledge API for the Wheel Loader programme, with a
command line and a tkinter desktop window on top. Version **0.8.4**, alpha. Named after
Melvil Dewey: one classification scheme, many views.

The idea, in one sentence: a database is the single source of truth, the Excel workbook
is a generated *view* of it, and everything a human can do through a front end an AI agent
can do through the same commands.

## What is in 0.8.4

- **The lock follows the siblings.** `uv.lock` takes asi_escher 0.1.3, asi_gutenberg 0.7.1 and
  asi_hopper 0.1.7, what their `main` branches declare and what CI checks out (it said 0.1.1, 0.6.0
  and 0.1.6). Nothing of Dewey's code changed: every name it imports from them exists unchanged at
  those versions, and the additions (`fill_docx`, the Confluence verbs) are not called here.

## What is in 0.8.3

- **The mouse wheel over a combobox no longer picks a value.** Scrolling a form with the pointer
  passing over a task class, a link class or any other dropdown changed it one step per notch,
  silently, and the next Save stored it (Tk's stock `TCombobox` binding; asi_kletz 0.15.2 found
  it in the owner's Safety Plan). The window drops that binding and the spinbox's once at start:
  the wheel scrolls, a value changes by a pick or a keystroke only.

## What is in 0.8.2

The scrollbar's slider, the thumb a person drags, is the palette's dimmed primary at rest and the
full primary (the neon) under the pointer, instead of the panel colour that made it vanish into
its trough. One line of the family theme recipe (`gui/theme.py`), the same in the sister tool.

## What is in 0.8.1

- **The JIRA Live Data screen is gone from the window**, by the owner's instruction of 2026-10-28,
  with its comments window and the `jira_live_autofetch` key. The window has ten screens: Dashboard,
  the seven entity screens, Export / Import, Generate; the `JIRA TICKETS` tile counts the cache and
  opens nothing. Nothing of the command line changed: `jira sync`, `jira status`, `jira get`,
  `jira live` and `jira comments` are as they were (see [Jira](#jira)). asi_kletz keeps its window.

## What is in 0.8.0

- **Every row has a hidden `uid`**, assigned once on creation, never shown, never changed, in every
  file the tool writes and honoured by every import (the JSON dump as a key, the workbook as a
  hidden last column of every sheet). A 0.7.x database opens as 0.8.0 with every row stamped and
  nothing else changed (schema version 2). `get`, `update` and `delete` accept a uid where an id
  is expected; see [Identity](#identity). Same convention in asi_kletz.
- **No table shows `id` or `order`.** The entity screens show the fields; the details frame says
  which row is selected (`Task details · row 2`) and the status bar still says `Task 2 selected`.
  `order` stays in the form and stays the default sort.

## What is in 0.7.4

- **Links are clickable.** On the Links and QMS Documents screens (every URL field: `link text`,
  `QMS link`, the Jira ticket link) a click on the URL cell in the table opens it in the browser
  and selects the row, and the pointer is a hand over it; in the form, Ctrl+click on the URL text
  opens it, beside the Open button that was already there. The status bar names what was opened
  (`Open: <url>`); with `interactive=False` nothing opens and only the line is written.

## What is in 0.7.3

- **The JIRA Live Data window no longer freezes while it fetches**: `jira live` runs on a worker
  thread (`MainWindow.execute_quiet`) and the Tk thread polls and paints the Result; meanwhile the
  label says "Fetching Jira … up to 2000 issues, this can take a minute", Refresh is disabled, and
  a theme pick or a close never waits on Jira. The comments window fetches the same way.
- **No automatic connection**: `jira_live_autofetch` now defaults to `false`; the window shows
  "No fetch yet · press Refresh" until you press Refresh, unless `dewey.toml` says `true`.

## What is in 0.7.2

- A documentation sweep, no code change: the version line above (it still said 0.6.0), the
  Requirements and Layout sections (asi_hopper, `locks.py`, `errors.py`, `version.py`, every test
  file), the CHANGELOG's compare links, and the plans in `docs/` that still described screens
  removed in 0.4.0 or work that shipped since. See `CHANGELOG.md`.

## What is in 0.7.1

- **Every table column fits its widest text**, heading and lookup values included: after each
  fill, the entity screens, the JIRA Live Data table and the dashboard tables measure every
  column with the real fonts and size it so nothing is clipped (an enum column also fits the
  longest value of its lookup, even when no row holds it). Same in asi_kletz.

## What is in 0.7.0

- **The local automation server.** A running window serves JSON over `127.0.0.1` on an
  ephemeral port, with a per-launch bearer token in `%LOCALAPPDATA%\asi\dewey\session.json`.
  `asi-dewey ...` while a Dewey window is open is no longer refused: the command is forwarded
  to the window, runs on its Tk thread, refreshes the open screen, and its `Result` is printed
  exactly as if it had run locally (exit 0 or 1). `GET /status`, `POST /execute`,
  `GET /screens`, `POST /screen`, `GET /events?since=<n>`, `POST /quit`; `asi-dewey session`
  reports the session and `session --quit` closes the window; `--no-server` and
  `ASI_DEWEY_AUTOMATION=off` turn it off. The status bar shows the port in the online indicator
  and a one-word **theme badge** (`CYAN NEON`); `asi-dewey theme pink-day` from another console
  recolours the open window, unless the open screen has unsaved edits (refused, never a dialog).
  See [Automation](#automation) and `docs/automation-server-plan.md`.

## What is in 0.6.0

- **One primary tool at a time.** While any process of Dewey or [asi_kletz](../asi_kletz)
  holds an open `Brain`, no other process of either tool may open one: a second `asi-dewey`
  command while the window is open is refused with exit code 3 and a JSON `Result` naming the
  holder (tool, pid, since, database), the window shows a Retry / Quit dialog, and
  `--wait <seconds>` queues for the slot instead. `PrimaryToolBusy` is the Python exception;
  `status` reports `lock_dir` and `locks`; the About box names the lock directory. The lock is
  an OS advisory lock the OS releases when the process ends, so a crash never leaves a stale
  one. Both tools implement the same convention, written once in `ASI_FUSA_TOOLS.md`. See
  [One at a time](#one-at-a-time) and `docs/single-instance-plan.md`.

## What is in 0.5.0

- **The JIRA Live Data window** (removed in 0.8.1; the verbs stay), second in the navigation list
  and in `View`, right below the Dashboard: one Refresh button and one big table of every HWL
  issue, past and present, with status and category, sortable on any column, done rows dimmed,
  and local filters (a text box on key or summary; Status, Category, Type, Priority, Assignee).
  A `[Comments]` cell on every row opens that ticket's **comments window**, newest first. Two
  new actions on the `jira` verb feed them, `jira live` and `jira comments <key>`; nothing is
  written to the database. The same window, by convention, exists in [asi_kletz](../asi_kletz).
  See `docs/jira-live-data-plan.md`.
- Windows in nav order: Dashboard, JIRA Live Data, Tasks, Facts, Machine Functions, Use Cases,
  Links, QMS Documents, People, Export / Import, Generate. The `JIRA TICKETS` tile on the
  dashboard opens the live window. (Since 0.8.1: no JIRA Live Data, and the tile opens nothing.)

## What is in 0.4.0

- **Fewer windows.** The JIRA, Safety Plan and Safety Plan Matrix screens are gone from the
  navigation list and the View menu. The `jira_ticket` and `safety_plan_row` entities stay,
  with their tables, workbook sheets, `dump` / `load`, the `jira` verb and the dashboard tile
  (the count is kept; the tile no longer opens a screen). The Safety Plan is edited in
  [asi_kletz](../asi_kletz); the live Jira view follows in 0.5.0. `HIDDEN_ENTITY_SCREENS` in
  `gui/screens.py` names the entities that have no screen. See `docs/prune-windows-plan.md`.

## What is in 0.3.0

- **The family palette**: 32 themes (8 hue families x 4 tones, `cyan-noir` to `green-day`)
  shared by name with the sibling tools, plus `plain`. Dewey's house default is `cyan-neon`
  (the former `tron`, now an alias of it). A **theme picker** at the foot of the navigation
  column and a `View > Theme` menu repaint the window at once and **latch** the choice per
  person and per machine; a new verb `theme` does the same from the command line. See
  [Themes](#themes).

## What is in 0.2.0

- **Diagrams and documents generated from the database** through two new verbs, `diagram`
  and `document`, built on the sibling generators [asi_escher](../asi_escher) and
  [asi_gutenberg](../asi_gutenberg). Four diagrams (`schema_map`, `lifecycle_overview`,
  `phase_flow`, `task_flow`) and three documents (`safety_plan`, `status_report`, `handbook`)
  live in catalogs behind `DiagramFactory` and `DocumentFactory`; a new one is a builder
  function plus a decorator. See [Diagrams and documents](#diagrams-and-documents).
- A third configurable path, `out`, for the generated files, and a **Generate** screen in the
  window (File > Build document…).

## What is in 0.1.0

- **Desktop window** (`asi-dewey gui` or `asi-dewey-gui`): navigation on the left, one screen
  at a time on the right. A Dashboard (row counts, open Jira tickets, tasks ending this week,
  recent changes), a generic table-plus-form screen for every entity generated from its
  schema (since 0.8.0 its table shows no `id` or `order` column and the details frame names
  the selected row), a Safety Plan Matrix where a click toggles a flag (the Safety Plan Matrix
  screen was removed in 0.4.0), and an Export / Import screen.
  Ctrl+N new, Ctrl+S save, Ctrl+E export workbook, F5 refresh. The window only ever calls
  `Brain.execute` with actor `gui`, so the audit log records it like any other actor, and the
  event bus refreshes the open screen when the CLI or an agent changes data on the same Brain.
- **Themes** from a `ThemeFactory`. The default, `tron`, is dark with cyan light lines, orange
  for whatever is active, a geometric heading face and a monospace status line; `plain` keeps
  the native look. Pick one with `asi-dewey gui --theme plain` or `ASI_DEWEY_THEME=plain`.
  (Since 0.3.0 `tron` is an alias of `cyan-neon`, one of 32 palettes; see [Themes](#themes).)

## What is in 0.0.0

- **Nine entities**, declared once in `asi_dewey/schema/definitions.py` and seeded from
  the sheets of the workbook: tasks, facts, machine functions, use cases, links, Jira
  tickets, QMS documents, people, and the Safety Plan matrix (63 columns, including the
  location, reference, author, verification, and reviewer flag groups).
- **SQLite storage** generated from those declarations, with automatic column migration,
  a schema fingerprint table, and an **audit log** that records who did what.
- **One command path**: `list`, `get`, `create`, `update`, `delete`, `count`, `schema`,
  `status`, `dump`, `load`, `export`, `import`, `run`. Every command returns a structured
  `Result` (`ok`, `data`, `errors`, `warnings`) that serialises to JSON.
- **JSON dump and load** with `replace`, `merge`, and `append` modes.
- **Excel export** that regenerates the workbook (bold headers, frozen row, autofilter,
  hyperlinks, date formats, dropdowns from lookups) and **Excel import** that reads it back,
  including the original workbook for seeding.
- **Event bus** so a future GUI can refresh live, and a **script runner** that replays a
  `.jsonl` of commands.
- Factories and registries everywhere: `SchemaRegistry`, `ModelFactory`, `StorageFactory`,
  `RepositoryFactory`, `CommandFactory`, `ExporterFactory`, `ImporterFactory`. A new entity,
  command, or format is added by registration, not by editing core code.

Not yet: approval mode, `fill` / `submit` / `cancel` puppeting of a screen's form. See `CHANGELOG.md`.

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- `openpyxl` (Excel views)
- the sibling checkouts `../asi_escher` and `../asi_gutenberg` (diagram and document views);
  they bring matplotlib, Pillow, reportlab and python-docx, all imported lazily
- the sibling checkout `../asi_hopper` (Jira, read only: `jira sync`, `jira live`, `jira comments`);
  imported lazily too
- `pytest` for the test suite

## Install

```powershell
cd asi_dewey
uv sync
```

That creates `.venv` with the package installed in editable mode and the `asi-dewey` and
`asi-dewey-gui` commands on `.venv\Scripts`. Without uv: `python -m venv .venv` then
`.venv\Scripts\python -m pip install -e .` and `pip install pytest`.

## Configuration

`asi-dewey` looks for `dewey.toml` in the working directory (or at `$ASI_DEWEY_CONFIG`):

```toml
db = "dewey.db"
workbook = "../some folder/workbook.xlsx"
out = "../some folder/generated"
```

Relative paths resolve against the config file, so the workbook and the generated diagrams
and documents can go to another folder, for example a shared one. The file is git-ignored
because it is specific to one machine; copy `dewey.example.toml` to start. Precedence for
every path is the explicit argument (`--db`, `--out`), then the environment (`ASI_DEWEY_DB`,
`ASI_DEWEY_WORKBOOK`, `ASI_DEWEY_OUT`), then `dewey.toml`, then `./dewey.db`, `dewey.xlsx`
and `out/` next to the database. `status` reports all three as `database`, `workbook_path`
and `out_dir`. Two more keys are plain settings, not paths: `jira_jql` (what `jira sync`
caches) and `jira_live_jql` (what `jira live` fetches); see [Jira](#jira) and
`dewey.example.toml`. `jira_live_autofetch` (0.7.3 to 0.8.0) is ignored since 0.8.1, with any
other unknown key.

## Quick start

Seed the database from the workbook, look around, regenerate the workbook:

```powershell
asi-dewey import excel "dewey.xlsx" --mode replace
asi-dewey status
asi-dewey list jira_ticket --filter status=open
asi-dewey create fact --set name="Project code" --set text=PRJ-0001
asi-dewey update task 3 --data '{"comments": "done", "end": "2026-10-27"}'
asi-dewey export excel --out "dewey.xlsx"
asi-dewey dump --out dewey.json
```

Open the window on the same database (add `--theme plain` for the native look, this launch
only; see [Themes](#themes)):

```powershell
asi-dewey gui
```

The database and workbook locations come from `dewey.toml` (see Configuration). If the
workbook is open in Excel, the export writes a timestamped sibling and says so in `warnings`.

Entity names accept the Python name, the table, the label, or the sheet name, so
`list "WL functions"` and `list machine_function` are the same thing. `schema` prints every
entity, field, lookup, and command signature; `schema safety_plan_row` prints one.

## Themes

The window is painted by one of 33 themes: the **family palette** of 32, shared by name with
the sibling ASI tools (the convention lives in `ASI_FUSA_TOOLS.md`; `gui/palettes.py` is the same
data in every tool, and a test checks its digest), plus `plain`, the native look.

The palette is 8 hue families x 4 tones. Families, in catalog order: cyan, blue, violet, pink,
red, amber, gold, green; each carries one accent colour for the live element (cyan carries
orange, pink carries cyan, and so on). Tones, darkest first: `noir` (near-black, tinted, deep
primary), `neon` (near-black, full neon: the classic look), `dusk` (charcoal, less glare), and
`day` (pale, white fields, dark lines on light). The key is `<family>-<tone>` and the title is
`<Family> <Tone>`: `pink-noir` is "Pink Noir", `pink-day` is "Pink Day". Dewey's house
default is `cyan-neon`; `tron` is kept as an alias of it, so nothing changes until you pick.

**Picking.** The `THEME` drop-down at the foot of the navigation column (or `View > Theme`)
always shows the theme that is painting the window. Picking another repaints the window at
once and **latches** the choice: it survives a restart and holds until you pick again. Each
tool latches on its own, so a pick in Dewey never changes Kletz. The same from the command
line:

```powershell
asi-dewey theme              # the catalog, the latched key, the resolved key, the prefs path
asi-dewey theme pink-noir    # latch pink-noir (and repaint a window open in this process)
asi-dewey theme --list       # the same as no key
```

An unknown key is a `Result.failure` (exit 1) and changes nothing. A latch publishes the
`theme.changed` event.

**Where the latch lives.** A theme is a per-person, per-machine preference, not a project
setting, so it is not in `dewey.toml` and not in the database. It is one flat JSON object
(`theme`, `tool`, `version`, `updated_at`) at `$ASI_DEWEY_PREFS` if set (a full file path),
else `%LOCALAPPDATA%\asi\dewey\prefs.json` on Windows, else `$XDG_STATE_HOME/asi/dewey/prefs.json`,
else `~/.local/state/asi/dewey/prefs.json`. A missing or corrupt file is ignored; an unknown
key in it is ignored with a warning in the status bar and overwritten by the next pick.

**Precedence when the window opens:** `--theme` argument, then `$ASI_DEWEY_THEME`, then the
latched preference, then the house default `cyan-neon`. The argument and the environment
variable are one-off views and never write the preference; only a pick, or the `theme` verb,
latches.

## Jira

Jira tickets come from Jira, read only, through the sibling [asi_hopper](../asi_hopper). Sign in
once with `asi-hopper auth login` (OAuth in the browser, no API token), then:

```powershell
asi-dewey jira sync --dry-run true      # what would change, nothing written
asi-dewey jira sync                     # upsert by issue key into jira_ticket, audit action jira:sync
asi-dewey jira status                   # rows, counts by status, last sync, asi_hopper session
asi-dewey jira get HWL-2572             # one live issue and the row it maps to
asi-dewey jira live                     # a live table of issues, held in memory, never stored
asi-dewey jira comments HWL-2572        # one issue's comment history, newest first
```

The JQL comes from `--jql`, else `jira_jql` in `dewey.toml`, else the built-in default (open
HWL issues you are assigned to or watch). Rows with a `key` are a cached view of Jira; rows
without one are yours and are never touched. A key the JQL no longer returns is reported as
stale, never deleted. Jira's status category maps to the `jira_status` lookup; `blocked` only
when Jira itself says Blocked. The `JIRA` sheet of the workbook carries the new columns.

### `jira live` and `jira comments`

Two read-only fetches held in memory, never stored, never audited. The window that showed them
(the JIRA Live Data screen of 0.5.0 and its comments window) was removed in 0.8.1 by the owner's
instruction; asi_kletz keeps its window, and the row shape below is the convention both tools
share (`docs/jira-live-data-plan.md`, section 3.1).

```powershell
asi-dewey jira live --jql "project = HWL AND type = Bug"   # one-off JQL
asi-dewey jira live --limit 300                             # cap the fetch; `truncated` is reported
asi-dewey --compact jira live | jq '.data.issues[] | .key'
```

`jira live` takes `--jql` (else `jira_live_jql` in `dewey.toml`, else
`project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC`) and `--limit` (default 2000; a longer result is cut,
`truncated` is `true` and a warning says so). Its data is `jql`, `fetched_at` (UTC), `count`,
`truncated` and `issues`, one dict per row with the sixteen keys `key`, `issue_type`, `summary`,
`status`, `status_category`, `resolution`, `priority`, `assignee`, `reporter`, `labels`,
`components`, `parent_key`, `created`, `updated`, `due`, `url` (lists for labels and
components, strings or `null` elsewhere). It publishes `jira.live` (`jql`, `count`,
`truncated`, `fetched_at`, `actor`) and writes neither a row nor an audit entry. `jira comments
<key>` returns `key`, `summary`, `url`, `status`, `fetched_at`, `count` and `comments` (`id`,
`author`, `created`, `updated`, `body`), newest first, and publishes nothing. Both fail like
`get`: `asi_hopper` missing, no Atlassian session, or `Jira read failed: ...`.

## Python API

```python
from asi_dewey import Brain

with Brain("dewey.db") as brain:
    result = brain.execute("create", entity="task", data={"name": "Write FSC", "task_class": "deliverable"})
    print(result.ok, result.data["id"], result.warnings)

    # services are also available directly
    rows = brain.service("task").list(filters={"task_class": "status"}, order_by="-order")

    # the wire format an agent would send
    brain.execute_dict({"verb": "get", "args": {"entity": "task", "id": 1}, "actor": "claude"})

    brain.events.subscribe("*", lambda topic, event: print(topic, event["entity"]))
```

### Identity

Every row has two names. The integer `id` is the handle: it is typed in commands
(`update task 2 …`), it is the row iid of every tree, the audit log's `entity_id` and the status
bar's "Task 2 selected". The `uid` is the trace: a lowercase UUID4 with dashes, assigned once by
`create`, never shown in a table or a form, never changed, written to every file the tool writes
(a key of every row in the JSON dump, a hidden last column of every workbook sheet) and honoured
by every import, so a row keeps its identity across a dump, a workbook edited in Excel or a
Kletz plan imported here. Wherever a command takes an id it also takes a uid: `get task 2` and
`get task 3f1c…` are the same row; `update task <uid> --set uid=…` fails with `uid is immutable`;
`list task --filter uid=…` works as for any field. The convention is shared with asi_kletz by name
(`docs/hidden-identity-plan.md`, section 3.1).

## Scripts

A script is one JSON object per line:

```jsonl
{"verb": "create", "args": {"entity": "fact", "data": {"name": "ASI Project Code", "text": "PRJ-0001"}}}
{"verb": "export", "args": {"format": "excel"}}
```

Run it with `asi-dewey run steps.jsonl` (add `--stop-on-error true` to halt at the first failure).
A script runs inside one `Brain`, so it is one instance of the tool (see [One at a time](#one-at-a-time)).

## One at a time

At most one primary tool runs at a time, and the same tool never runs twice: while any process
of Dewey or asi_kletz holds an open `Brain` (the window for its session, the CLI for the
milliseconds a command takes, a Python caller between `Brain(...)` and `close()`), no other
process of either tool may open one. One process may hold several `Brain` objects; the slot is
released when the last one closes. This gives every SQLite database exactly one writer and a
definite answer to "who has the database open"; it does not reach across machines or user
accounts, and it does not change how OneDrive treats files.

What you see when the slot is taken:

```powershell
asi-dewey status            # while the Dewey (or Kletz) window is open
# {"ok": false, "verb": "status", "data": {"slot": "family", "holder": {"tool": "asi_dewey", "pid": 18432, ...}},
#  "errors": ["asi_dewey is running (pid 18432, since 2026-10-27T17:02:11+00:00, db C:\...\dewey.db); only one
#             primary tool may run at a time. Close it, or retry with --wait."], "warnings": []}
# exit code 3 (1 still means "the command ran and failed")
asi-dewey --wait 30 status  # poll every 250 ms for up to 30 s, then refuse the same way
asi-dewey-gui --wait 30     # the window waits too, then shows a Retry / Quit dialog
```

The lock lives outside every repo and every synced folder: `%LOCALAPPDATA%\asi\locks` on
Windows (`$XDG_STATE_HOME/asi/locks` or `~/.local/state/asi/locks` elsewhere), or
`$ASI_PRIMARY_LOCK_DIR`, the one environment variable the primary tools deliberately share.
`primary.lock` is the family slot, `db-<sha1>.lock` the slot of one database (none for
`:memory:`), and the `.json` beside each names the holder (`tool`, `version`, `pid`,
`started_at`, `db`, `cwd`, `host`, `user`); the lock is an OS advisory lock
(`msvcrt.locking` / `fcntl.flock`) that the OS releases when the process ends, so a crash never
leaves a stale lock. There is no override flag; pointing `ASI_PRIMARY_LOCK_DIR` at a private
directory is the only escape, and it is what the test suite does. `status` reports `lock_dir`
and `locks`; Help > About names the directory.

Agents: an agent that drives Dewey and Kletz runs them **one after the other**, with `--wait`
when it cannot know whether a window is open; data moves between the tools sequentially through
`dump` in one and `load` in the other, never by holding both open. A refusal in favour of a
**Dewey window** is not the end of the story: since 0.7.0 the CLI forwards the command to that
window's automation server (see [Automation](#automation)), so `asi-dewey ...` keeps working
while the window is open; a Kletz window is still exit 3. A Python caller catches
`asi_dewey.PrimaryToolBusy` (`slot`, `holder`) and should use the context manager so the slot is
released as soon as the work is done.

## Automation

A running window owns a small HTTP server on `127.0.0.1`, bound to an ephemeral port, so an
agent (or a second console) can drive the session the engineer is looking at. Nothing is
installed for it: `http.server` on a daemon thread, JSON `Result` answers, no TLS (loopback
only). The convention is shared with asi_kletz (`ASI_FUSA_TOOLS.md`, "The automation session").

**The session file.** `%LOCALAPPDATA%\asi\dewey\session.json`, beside `prefs.json`
(`$XDG_STATE_HOME/asi/dewey/session.json` elsewhere; `$ASI_DEWEY_SESSION` overrides the full
path), written once the server has bound and removed when the window closes:

```json
{"tool": "asi_dewey", "version": "0.7.0", "pid": 18432, "started_at": "2026-10-27T17:02:11+00:00",
 "host": "127.0.0.1", "port": 51234, "address": "http://127.0.0.1:51234",
 "token": "3f9c...32 hex...", "db": "C:\\...\\dewey.db"}
```

`pid` and `started_at` are the values the lock holder writes to `primary.json`, so the two files
match. Every reader ignores the file when its `pid` is not alive, so a file left by a crash is
harmless and the next window overwrites it.

**The endpoints.** Every request carries `Authorization: Bearer <token>`; a wrong or missing
token is 401 with `errors[0] == "bad token"`, a request with an `Origin` header is 403 (a browser
page never gets in, token or not). The HTTP status is about transport: a failed command is 200
with `ok: false`, the same as the CLI printing it and exiting 1; 504 means the window did not
answer within 60 s.

| Method and path | Body | `Result.data` |
|---|---|---|
| `GET /status` | none | `tool`, `version`, `pid`, `db`, `screen` (the open key), `theme` (`key`, `title`), `started_at`, `uptime_s`, `port`, `requests`, `events_seq`, `lock` (the holders, as `status` reports them) |
| `POST /execute` | `{"verb": "list", "args": {"entity": "fact"}, "actor": "agent"}` | the command's own `Result`, `verb` included; actor `agent` unless given; `gui` is refused |
| `GET /screens` | none | `{"screens": [{"key", "title", "current"}, ...]}` in navigation order |
| `POST /screen` | `{"show": "entity:fact"}` | `{"screen", "title"}`; an unknown key is `ok: false` |
| `GET /events?since=<n>&limit=<m>` | none | `{"since", "seq", "events": [...]}`: the events after sequence `n` (default 0), at most `m` (default 200); a warning when the history no longer reaches back to `n` |
| `POST /quit` | none | `{"quit": true}`; the window closes 100 ms later |

Every event on the bus carries `seq`; polling `/events` with the last `seq` seen is the protocol,
nothing is pushed. A command run through `/execute` runs on the window's Tk thread with the
actor the agent sent, the audit log records it, and the open screen refreshes as it does for
any other change.

```powershell
$s = Get-Content $env:LOCALAPPDATA\asi\dewey\session.json | ConvertFrom-Json
$h = @{ Authorization = "Bearer $($s.token)" }
Invoke-RestMethod "$($s.address)/status" -Headers $h
Invoke-RestMethod "$($s.address)/execute" -Method Post -Headers $h -ContentType application/json `
  -Body '{"verb": "create", "args": {"entity": "fact", "data": {"name": "from an agent"}}, "actor": "agent"}'
Invoke-RestMethod "$($s.address)/screen" -Method Post -Headers $h -ContentType application/json -Body '{"show": "entity:fact"}'
```

**Forwarding.** `asi-dewey <verb> ...` while a Dewey window is open no longer stops at the lock:
when the refusal names a window of this tool whose session file is alive and whose `/status`
answers with that pid, the command is posted to `/execute` with `--actor` and the forwarded
`Result` is printed untouched, exit 0 or 1 by its `ok`. Nothing marks it as forwarded: an agent
learns one dialect. A Kletz window is still exit 3 (one tool never drives the other's window);
a window started with `--no-server` or `ASI_DEWEY_AUTOMATION=off` is exit 3 with the hint
`no automation session; ...`; a session that does not answer is exit 3 with `... did not answer`
(never 1: the command did not run). `--no-forward` turns the branch off, and then `--wait` queues
for the slot as in 0.6.0. `--db` naming another database than the window's is ignored with a
warning on stderr.

**`asi-dewey session`** is the one verb that opens no database, so it works while the window
holds the lock: it prints the file's path, `present`, `alive` (the pid), `reachable` (`/status`
answered), the session (`pid`, `port`, `address`, `started_at`, `db`; never the token) and the
`/status` data. `asi-dewey session --quit` asks the window to close and waits up to 5 s for the
file to go; with no live session it is `ok: false`.

**Remote recolour.** `asi-dewey theme pink-day` from another console (or `/execute` with the
`theme` verb) repaints the open window at once and the badge says `PINK DAY`. A remote pick never
prompts: when the open screen has unsaved edits it is refused with `theme change refused: ...`
and the preference is not latched, so the window and the latch stay in step. `MainWindow.remote_guard`
is the hook; it is a safety rule, not a permission system (approval mode is the next plan).

**Off switch.** `asi-dewey-gui --no-server` (or `gui --no-server`) for one launch,
`ASI_DEWEY_AUTOMATION=off` for every launch. The window is fully usable either way; the status
bar reads `◉ ONLINE` without a port, and the CLI is refused with exit 3 as in 0.6.0.

**Security.** Loopback only, so another machine cannot reach the server by construction. The
token is 128 bits from `secrets`, new on every launch, and lives in a file under the user's
profile (`0o600` on POSIX), so another local *account* cannot read it and cannot drive the
window; a web page in the engineer's browser is refused by the `Origin` rule even with the token.
A process of the **same** user is trusted: it can already open the database file directly, so the
token adds nothing against it and is not meant to. The server runs registered verbs through the
dispatcher and shows registered screens; there is no eval and no file path beyond what the verbs
already accept. Every remote command carries its actor into the audit log.

## Diagrams and documents

Like the workbook, a diagram or a document is a **view**: regenerated from the database on
demand, never read back. Dewey builds diagrams with [asi_escher](../asi_escher) and documents
with [asi_gutenberg](../asi_gutenberg) through the same command path as everything else, so
the CLI, the window, a `.jsonl` script and an agent calling `Brain.execute_dict` all do the
same thing.

```powershell
asi-dewey diagram                                   # the diagram catalog (keys, params)
asi-dewey diagram schema_map --out out              # out/schema_map.{png,svg,dot,mmd}
asi-dewey diagram phase_flow --param phase=3        # a required param, by leading number or full label
asi-dewey diagram task_flow --formats png,mmd --dpi 200
asi-dewey document                                  # the document catalog
asi-dewey document safety_plan --out out            # out/safety_plan.{md,pdf,docx} + out/figures/*.png
```

| Diagram | What it shows | Params |
|---|---|---|
| `schema_map` | one SysML block per registered entity with its field and row counts; works on an empty database | none |
| `lifecycle_overview` | the lifecycle phases chained left to right, each with its deliverable count and done count; a phase with a Blocked row is tinted | none |
| `phase_flow` | one phase's deliverables as an activity diagram with Author, Verification and Reviewer lanes | `phase` (required) |
| `task_flow` | tasks in start-date order, one lane per task class; past tasks tinted | `class` (optional) |

| Document | Kind | Content |
|---|---|---|
| `safety_plan` | plan | purpose, lifecycle overview table and figure, one section per phase with Deliverables and Ownership tables and a phase flow figure, appendices for roles, QMS references and the status legend. A **working copy**: the controlled Safety Plan is asi_kletz's. |
| `status_report` | report | row counts, open Jira tickets, tasks ending within seven days, recent changes, task flow and lifecycle figures |
| `handbook` | report | facts, people by class, links, QMS documents, machine functions, use cases, schema map appendix |

Every `Result` carries the written `paths`, a `primary` file (the PNG, or the PDF), and `issues`
(Escher layout problems or Gutenberg trace problems, also repeated as `warnings`). A document
result adds `pages`, `stats` and `diagrams`, one entry per figure. The author of a document is
the actor that ran the command (`cli`, `gui`, `claude`, …), the project is the fact named
`Product` if there is one, and the status is Draft. Every build is audited (action `generate`)
and published as a `generated` event. A locked PDF (open in a viewer) is written to a
timestamped sibling, like the workbook.

In the window, the **Generate** screen lists both catalogs, builds a parameter form from the
spec (a lookup combobox for `phase`), and offers Build, Open file and Open folder.

Adding a diagram or a document is one function and one decorator; builders read the database
only through `brain.service(entity)` and `brain.registry`:

```python
from asi_dewey.generate import Param, Spec, register_diagram

@register_diagram(Spec("open_tickets", "Open Jira tickets", "One node per open ticket.",
                       params=(Param("status", "Ticket status", default="open", lookup="jira_status"),)))
def open_tickets(brain, params):
    from asi_escher import Diagram  # lazy: keeps start-up light
    d = Diagram("Open Jira tickets", "flowchart")
    for ticket in brain.service("jira_ticket").list({"status": params["status"]}):
        d.action(f"t{ticket['id']}", ticket["name"])
    return d
```

A document builder returns an `asi_gutenberg.Document` and adds catalog diagrams with
`asi_dewey.generate.figures.add_figure(doc, brain, "lifecycle_overview", caption=...)`, which
attaches an Escher diagram block that Gutenberg renders into `figures/` beside the Markdown.

## Layout

```
src/asi_dewey/
  version.py          __version__ and SCHEMA_VERSION, the single source of truth
  errors.py           BrainError and its family (NotFound, ValidationError, CommandError, PrimaryToolBusy)
  brain.py            Brain: wires everything, the in-process API, dewey.toml loading
  locks.py            the family lock: one primary tool at a time, $ASI_PRIMARY_LOCK_DIR
  prefs.py            per-person preferences (the latched theme) in prefs.json, $ASI_DEWEY_PREFS
  schema/             FieldSpec, EntitySchema, lookups, registry, definitions (the 9 entities)
  models/             ModelFactory (dataclasses from schemas)
  storage/            Storage interface, SQLite backend, migrations, audit log, StorageFactory
  repositories/       SqlRepository, RepositoryFactory
  services/           EntityService (validated CRUD), TransferService (dump/load/export/import), shared queries
  commands/           Result, Command, CommandFactory, Dispatcher, built-in verbs
  io/                 JSON and Excel exporters and importers behind factories
  generate/           DiagramFactory, DocumentFactory, Spec/Param, the diagram and document catalogs, figures.py
  automation/         CLI (with forwarding), EventBus (seq), script runner, server.py (the loopback automation
                      server a window owns) and session.py (the session file the CLI reads to find it)
  gui/                tkinter: MainWindow, ScreenFactory, WidgetFactory, entity/dashboard/transfer/generate screens,
                      theme.py (ThemeFactory, GridTheme) and palettes.py (the family palette, pure data)
tests/                pytest suite (schema, core, transfer, generate, jira, locks, CLI, GUI, theme, server, session);
                      fixtures/dewey-0.7.4.db, a small 0.7.4 database for the open-and-stamp test
```

## Tests

```powershell
.venv\Scripts\python -m pytest
```

Tests never read the developer's `dewey.toml` or environment, so no test can touch a real
workbook. One test seeds a database from the workbook named in the repo's `dewey.toml` and
is skipped when there is none. The GUI tests drive real tkinter widgets with the window
withdrawn and are skipped when no display is available. pytest runs with `--capture=sys`
(see `pyproject.toml` for why). The family lock is tested in a per-test lock directory
(`ASI_PRIMARY_LOCK_DIR`), with holder subprocesses, including a simulated asi_kletz, so the
suite never touches the real lock directory and both tools' suites can run at the same time.
Every test window starts its automation server on `127.0.0.1` port 0 with `ASI_DEWEY_SESSION`
pointed at a per-test file, so no test reads or writes the real session file and a developer's
open window never receives test traffic; the Tk thread is the test thread, so the server tests
make their requests from a helper thread while pumping `window.update()`.

The files, one per layer: `test_schema.py`, `test_core.py`, `test_transfer.py`, `test_generate.py`,
`test_jira.py` (asi_hopper's replay fixtures; skipped when the sibling is not checked out),
`test_locks.py`, `test_cli.py`, `test_gui.py`, `test_theme.py`, `test_server.py` and
`test_session.py`; `conftest.py` holds the isolation fixture and the `brain`, `seeded` and `hold`
fixtures. `test_core.py` opens a copy of `tests/fixtures/dewey-0.7.4.db` (never the file itself) to
check that a 0.7.x database opens as 0.8.0 with every row stamped and nothing else changed.

## Adding an entity

Declare it and register it. Tables, commands, JSON, and the Excel sheet follow.

```python
from asi_dewey.schema import EntitySchema, FieldSpec, FieldType, register_entity

register_entity(EntitySchema(
    name="hazard", table="hazards", label="Hazard", sheet="hazards",
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", FieldType.INT, "hazard order"),
        FieldSpec("name", FieldType.TEXT, "hazard name", required=True),
        FieldSpec("severity", FieldType.ENUM, "severity", lookup="severity"),
    ),
))
```

Import the module before creating a `Brain`; the next `Brain(...)` adds the table. Every entity
ends with the hidden `uid` field: `EntitySchema` appends it, so a declaration never names it (one
that does must put it last, hidden, as `TEXT`).
