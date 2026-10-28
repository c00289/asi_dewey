# Changelog

All notable changes to ASI Dewey are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0 releases may break anything.

## [Unreleased]

### Planned
- Approval mode: human confirms agent commands before they commit (behind `remote_guard`).
- Excel import diff preview; `fill` / `submit` / `cancel` puppeting of a screen's form; a
  `View > Automation` submenu or screen; date picker widget.

## [0.7.4] - 2026-10-28

Links in Links and QMS Documents were not clickable, reported by the owner on 2026-10-28. Schema
version unchanged (1).

### Added
- **Clickable URL cells** on every entity screen with a URL field (Links `link text`, QMS Documents
  `QMS link`, Jira Tickets `JIRA link`): `EntityScreen.url_columns` lists them; a `<Button-1>` on
  such a cell with a value selects the row and calls `EntityScreen.open_url`, which opens the
  browser when the window is interactive and writes `Open: <url>` on the status bar either way;
  `<Motion>` shows a `hand2` cursor over a link cell and nothing else changes. Any other cell keeps
  the normal selection. An empty URL cell is not a link.
- **Ctrl+click on the URL form field** opens it too (`UrlWidget`, bound on the entry; the caption
  says so), and the Open button now reports through the same `open_url` (the widget takes an
  `opener` option; `webbrowser.open` stays the default when no screen provides one).

### Tests
- `test_url_cell_click_opens_the_link_and_selects_the_row`, `test_url_cell_without_a_value_is_not_a_link`,
  `test_url_widget_ctrl_click_and_open_report_through_the_screen` (the tree's `identify_*` are
  patched, as the comments-column test does, since a withdrawn window has no geometry to hit-test).

## [0.7.3] - 2026-10-28

The JIRA Live Data window froze while it fetched, and it fetched on its own. Schema version
unchanged (1).

### Fixed
- **The window froze during a live fetch.** `JiraLiveScreen.fetch` ran `jira live` on the Tk
  thread through `run_quiet`, and the house default pulls up to 2,000 issues at 50 a page, so the
  window stopped painting for the whole fetch (tens of seconds on a good link, minutes on a slow
  one or while asi_hopper waited on its gateway). The verb now runs on a daemon worker thread
  through the new `MainWindow.execute_quiet` (`Brain.execute` as actor `gui` and nothing else: no
  status bar, no dialog, no Tk call), and the Tk thread polls with `after(100, ...)` and applies
  the Result itself (`window.jira_live`, the status bar line "Jira: n issues fetched" or the
  failure text, `refresh()`), exactly as before. While a fetch runs the toolbar label says
  "Fetching Jira … up to 2000 issues, this can take a minute", Refresh is disabled and a second
  `fetch()` is ignored; a theme pick or a close never joins the worker (its Result is dropped when
  the screen is gone). The comments window fetches the same way ("Fetching comments …", its
  Refresh disabled meanwhile). The helper is `WorkerFetch` in `gui/screens.py`; `run_quiet` is
  now `execute_quiet` plus the status-bar report (`report_quiet`), so every other caller is
  unchanged.
- **The screen no longer connects on its own.** Opening JIRA Live Data (the nav entry, `View >
  JIRA Live Data`, the dashboard tile) paints "No fetch yet · press Refresh" and does nothing
  else unless `jira_live_autofetch = true` is in `dewey.toml`.
- `EventBus.publish` takes its counter and history under a lock: `jira.live` is now published
  from the worker thread while the Tk thread may publish too. Handlers still run on the
  publishing thread; `MainWindow._on_event` returns for `jira.live` before any Tk call, and
  `jira live` and `jira comments` are the only verbs the window runs off the Tk thread.

### Changed
- The house JQL now fetches only the issues that involve the person running the tool, past and
  present: `project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC`
  (it was every issue of the project). `jira_live_jql` in `dewey.toml` still overrides it.
- `jira_live_autofetch` defaults to **false** (was true): the window fetches on first show only
  when the key is explicitly `true`. The key stays in `dewey.example.toml` as the opt-in.
- `JiraLiveScreen.fetch` and `JiraCommentsWindow.fetch` return `None` (they start the worker);
  `wait_fetch(timeout=5.0)` is the test helper that pumps the Tk loop until the Result has been
  applied. The GUI tests stub `MainWindow.execute_quiet` instead of `run_quiet`.

## [0.7.2] - 2026-10-28

A documentation sweep. No code change beyond one docstring; schema version unchanged (1).

### Fixed
- README: the version line still said 0.6.0; Requirements did not list the sibling checkout
  `../asi_hopper`; the Layout tree lacked `version.py`, `errors.py` and `locks.py` and its `tests/`
  line named seven of the eleven test files; the Tests section now names every test file.
- CHANGELOG: the compare links at the foot stopped at 0.6.0 (0.3.0, 0.4.0, 0.5.0, 0.7.0 and 0.7.1
  had none, and `[Unreleased]` compared against 0.6.0).
- `brain.py` docstring said the front ends were "CLI today, GUI and local server later"; the
  window shipped in 0.1.0 and the server in 0.7.0.
- `docs/automation-server-plan.md`: status still "Draft 0.1 ... phase 5 lands in asi_fusa_tools"
  although the family section exists; its "What exists today" table listed `safety_plan_matrix`
  (removed in 0.4.0) and no `jira_live` without saying so.
- `docs/jira-live-data-plan.md`: the "What exists today" table listed `safety_plan_matrix` without
  "(removed in 0.4.0)" and described the family document as still at 0.2.0 with asi_hopper an empty
  folder and the lock plans at "Target 0.3.0"; the row now says that was the state when verified.
- `docs/escher-gutenberg-integration-plan.md`: status still "Draft 0.3, decided, ready to
  implement" for a plan that shipped as 0.2.0; its starting-point table now says it describes the
  tree before 0.2.0 and that the matrix screen went in 0.4.0.
- `docs/prune-windows-plan.md` and `docs/theme-palette-plan.md`: their "What exists today" tables
  describe the thirteen-screen window and the `tron` default of before; the headings now say so,
  the `gui/matrix_screen.py` mention says "(removed in 0.4.0)", and the theme plan's two open
  items (the theme badge, remote recolour) are marked shipped in 0.7.0.
- `docs/single-instance-plan.md`: section 1 said "after 0.3.0 the planned local automation server
  is the only way" (it shipped in 0.7.0, and the CLI forwards to it); the release phase still
  named 0.3.0 as the version to write into the CHANGELOG, `version.py` and `pyproject.toml`.
- `docs/plan.md`: the proposed layout of Draft 0.1 (flat package, Python 3.11+) now points at the
  real tree in the README; the open questions on naming and on how an agent puppets the window are
  marked answered (0.1.0, 0.7.0).

## [0.7.1] - 2026-10-27

### Changed
- The JIRA Live Data filters are a grid of three equal columns instead of one row that clipped at the
  right edge: find, status and category on the first row; type, priority and assignee on the second;
  the reset button and the count close it.
- Every table column fits its widest text, heading and lookup values included: `fit_columns`
  (`gui/screens.py`) measures each column of a `ttk.Treeview` in pixels with the real
  `Treeview` and `Treeview.Heading` fonts and sizes it to the widest heading, cell or extra
  value plus padding (40 to 600 px), so nothing is clipped. It runs after every fill of an
  entity screen (where an enum column also fits the longest value of its lookup, even when no
  row holds it), of the JIRA Live Data table (Summary still stretches) and of the three
  dashboard tables; the per-type widths of before are only the starting point. Same change in
  asi_kletz.

## [0.7.0] - 2026-10-27

The local automation server: JSON over localhost, so an agent can puppet a running session.
Since 0.6.0 the CLI is refused while a window is open, so the server is the only way to drive a
running window; `theme` is the first verb that recolours a running window remotely. Common by
convention with asi_kletz. See `docs/automation-server-plan.md` and the section "The automation
session" in `ASI_FUSA_TOOLS.md`.

### Added
- `automation/server.py`: `AutomationServer`, a `ThreadingHTTPServer` on `127.0.0.1` and an
  ephemeral port, served by a daemon thread the window owns. Every request carries
  `Authorization: Bearer <token>` (128 bits from `secrets`, new per launch); a wrong or missing
  token is 401 `bad token`, an `Origin` header is 403 (no browser page gets in), 404 / 405 / 400 /
  413 for the wrong path, method, body or size, 504 when the window does not answer, 500 when a
  job raises. The answer is always a JSON `Result`; a failed command is 200 with `ok: false`,
  exactly as the CLI prints it and exits 1. Endpoints: `GET /status` (tool, version, pid, db,
  screen, theme, started_at, uptime, port, requests, `events_seq`, `lock`), `POST /execute`
  (the dispatcher's `{"verb", "args", "actor"}`, actor `agent` by default, never `gui`; the
  `gui` verb is refused), `GET /screens`, `POST /screen {"show": key}`,
  `GET /events?since=<n>&limit=<m>`, `POST /quit`. **The main-thread handshake**: the handler
  queues every job and waits on an `Event`; the window drains the queue on the Tk thread every
  50 ms (`on_main`), so the server thread never touches a widget, the window's state or the
  Brain. The server never calls `run`, `pick_theme`, `confirm`, `notify_error`, `about` or
  `export_workbook`: nothing it does can open a dialog.
- `automation/session.py`: the session file `%LOCALAPPDATA%\asi\dewey\session.json` beside
  `prefs.json` (`$ASI_DEWEY_SESSION` overrides): `tool`, `version`, `pid`, `started_at`,
  `host`, `port`, `address`, `token`, `db`. `write_session` (atomic, `0o600` on POSIX),
  `read_session` (`None` when missing, corrupt, another tool, no token, or a dead pid),
  `clear_session` (only a file naming this pid), `pid_alive` (`OpenProcess` +
  `GetExitCodeProcess` on Windows, `kill 0` elsewhere), `probe` (`GET /status` must answer with
  the file's pid), `forward` (`POST /execute`), `automation_enabled` (`ASI_DEWEY_AUTOMATION`
  is not `off`).
- `EventBus`: every event carries `seq` (one counter per bus, from 1); `EventBus.seq`,
  `since(n, limit=200)`, `oldest_seq()`. `last(n)` is unchanged.
- The window: `MainWindow(..., server=True)` starts the server after the first screen is
  shown, writes the session file and shows the port in the online indicator (`◉ ONLINE :51234`;
  `◉ ONLINE` without a server); a failure to bind or to write the file is a status-bar warning,
  never a failed launch. `close()` stops the server and clears the session file before the root
  is destroyed, and is idempotent. The **theme badge** sits between the online indicator and
  the status text: the theme title upper-cased with any parenthetical dropped (`CYAN NEON`,
  `PINK DAY`, `PLAIN`), in the mono font, style `StatusMuted.TLabel`; `set_theme` rebuilds
  both labels and the server survives the rebuild. `remote_guard(verb, args)`: a remote
  `theme` pick never prompts; when the open screen reports `is_dirty()` it is refused with
  `theme change refused: the <screen> screen has unsaved edits` and the preference is not
  latched. The About box names the session address and file. `--no-server` on `asi-dewey-gui`
  and as a flag on the `gui` verb.
- The CLI forwards a refused command to a running Dewey window: when `Brain(...)` raises
  `PrimaryToolBusy`, the holder says `asi_dewey`, its pid is the session file's, the pid is alive
  and `GET /status` answers with it, the command goes to `POST /execute` with `--actor` and the
  forwarded `Result` is printed untouched, exit 0 or 1 by its `ok`. A Kletz holder is still
  exit 3; no session (or a wrong pid) is exit 3 with the hint `no automation session; the window
  may have been started with --no-server or ASI_DEWEY_AUTOMATION=off`; a session that does not
  answer is exit 3 with `the automation session at http://127.0.0.1:<port> did not answer`
  (never 1: the command did not run); `--no-forward` turns the branch off; `--db` naming another
  database than the session's is ignored with a warning on stderr.
- The `session` verb (`commands/session.py`), the one verb the CLI runs without opening a
  `Brain`: `asi-dewey session` reports `path`, `present`, `alive`, `reachable`, `session`
  (`pid`, `port`, `address`, `started_at`, `db`; never the token), `status` (the `/status`
  data) and `quit`; `session --quit` posts `/quit` and waits up to 5 s for the file to go
  (`ok: false` with no live session). Through `/execute`, or from Python inside the window's
  process, it reports the window's own session without a request to itself.
- Tests: `tests/test_server.py` (every endpoint over `urllib` against a real withdrawn window,
  the main-thread assertion, 401 / 403 / 404 / 405 / 400, the 504 timeout with the job still
  running afterwards, `/quit`, `--no-server` and the off switch, the remote recolour and the
  dirty refusal, the `session` verb in-process and from a second process),
  `tests/test_session.py` (the file, `pid_alive`, the forwarding branch with a monkeypatched
  refusal: same tool forwards, other tool / wrong pid / `--no-forward` / dead server are exit
  3, the `--db` warning), the `session` cases in `tests/test_cli.py`, the badge and indicator
  cases in `tests/test_gui.py`. `conftest.py` points `ASI_DEWEY_SESSION` at a per-test file and
  clears `ASI_DEWEY_AUTOMATION`, so no test touches the real session file and a developer's
  open window never receives test traffic.

### Changed
- The family document is now `asi_fusa_tools/ASI_FUSA_TOOLS.md` (titled "ASI FuSa Tools"); the
  digest test, the `palettes.py` and `locks.py` docstrings, and every link follow it.
- `asi-dewey ...` while a Dewey window is open now runs **in** that window (forwarded) instead
  of being refused; the open screen refreshes and the audit log records the CLI's actor. The
  refusal (exit 3) remains for a Kletz window and for a window without a session.
- Version 0.7.0. Schema version unchanged (1), no migration. No new dependency.

### Fixed
- JIRA Live Data never refreshed against the real site: a page of 100 issues with their descriptions
  rendered to Markdown is larger than the one-megabyte server-sent event Hopper's transport accepted.
  `jira live` now asks for `asi_hopper.LIST_FIELDS` only, 50 issues a page, and needs asi_hopper 0.1.1
  (configurable `gateway.max_event_mb`).

## [0.6.0] - 2026-10-27

One primary tool at a time: the family lock, common by convention with asi_kletz. See
`docs/single-instance-plan.md` and the section "One primary tool at a time" in `ASI_FAMILY.md`.

### Added
- `locks.py`: `lock_dir()` (`$ASI_PRIMARY_LOCK_DIR`, else `%LOCALAPPDATA%\asi\locks`, else the
  XDG state folder), `db_slot_name()` (`db-<sha1>` of the resolved, Windows-lower-cased path),
  `SlotLock` (one non-blocking OS advisory lock on byte 0, `msvcrt.locking` / `fcntl.flock`,
  plus the holder `.json` beside it: `tool`, `version`, `pid`, `started_at`, `db`, `cwd`,
  `host`, `user`), and `PrimaryGuard` with the one per-process instance `guard`: the family slot
  `primary.lock` and one database slot per path, reference-counted and thread-safe, so one
  process may hold several Brains and the slot is released when the last one closes. Family
  slot first, then database slot; a refused database slot gives the family slot back. The OS
  drops the lock when the process ends, so a crash never leaves a stale lock.
- `PrimaryToolBusy(BrainError)` in `errors.py`, exported from `asi_dewey`, with `slot`
  (`"family"` or `"database"`) and `holder` (the parsed `.json`, or `None`); its message names
  the holder: `asi_kletz is running (pid 4321, since 2026-10-27T17:02:11+00:00, db ...); only
  one primary tool may run at a time. Close it, or retry with --wait.`
- `Brain(..., wait=0.0)` takes the slots before `StorageFactory.create`, so a refused process
  never opens the SQLite file; `close()` releases them and is idempotent; `status()` reports
  `lock_dir` and `locks` (`family` and `database` holders). `:memory:` takes the family slot only.
- `--wait SECONDS` on `asi-dewey` and `asi-dewey-gui` (polling every 250 ms). The CLI prints a
  JSON `Result` with `ok: false`, `errors[0]` naming the holder and
  `data = {"slot", "holder"}` and exits with code **3** on refusal; 1 still means "the command
  ran and failed". The window shows a Retry / Quit dialog (`gui/app.py: ask_retry`); Retry
  re-attempts, Quit exits 3; `main(argv, interactive=False)` returns 3 without a dialog. The
  About box names the lock directory. No override flag.
- Tests: `tests/test_locks.py` (precedence, slot names, many Brains in one process, status, the
  memory database, a second process of the same tool, the simulated sibling that takes
  `primary.lock` with raw `msvcrt` / `fcntl` and writes `"tool": "asi_kletz"`, crash release,
  `wait`, database-slot refusal); refusal and `--wait` cases in `tests/test_cli.py` and
  `tests/test_gui.py`. `conftest.py` points `ASI_PRIMARY_LOCK_DIR` at a per-test directory and
  provides the `hold` fixture (holder subprocesses), so the suite never touches the real lock
  directory and the Dewey and Kletz suites can run at the same time.

### Changed
- `asi-dewey ...` while a Dewey or Kletz window is open is refused (exit 3) instead of writing
  under the window's feet; agents that drive both tools run them one after the other with
  `--wait`. Data moves between the tools sequentially through `dump` and `load` files.
- `.gitignore` ignores `*.lock` (except `uv.lock`), `primary.json` and `db-*.json` as a
  precaution; by convention no lock file is ever created inside a repo.
- Version 0.6.0. Schema version unchanged (1), no migration.

## [0.5.0] - 2026-10-27

The JIRA Live Data window and its comments view, common by convention with asi_kletz. See
`docs/jira-live-data-plan.md` and the section "The JIRA Live Data window" in `ASI_FAMILY.md`.

### Added
- Screen `jira_live` ("JIRA Live Data", `gui/jira_live_screen.py`), registered right after the
  dashboard so it is second in the navigation list and in `View`: a Refresh button, a status
  line (`n issues · fetched hh:mm · <jql>`), local filters (text on key or summary; read-only
  drop-downs for Status, Category, Type, Priority, Assignee with `(all)` and `(none)`; Clear
  filters), and a fifteen-column table with `[Comments]` first, sortable on every other heading
  (keys numerically, `None` last in both directions, `▲`/`▼` on the sorted heading), striped,
  done rows dimmed with the palette's `muted`. Double-click or Return opens the issue URL
  (`Open: <url>` in the status bar when not interactive); a click in the Comments column or `c`
  opens the comments window; `hand2` over the Comments cells.
- `gui/jira_comments_window.py`: `JiraCommentsWindow(tk.Toplevel)`, one per ticket, title
  `<KEY> — Comments`, 640x520, newest comment first, each body a disabled `tk.Text`, meta line
  `<author> · YYYY-MM-DD HH:MM` plus `· edited ...`, Refresh / Close, Escape and F5;
  `No comments.` for an empty history. A failed refresh keeps the blocks and the window.
- Actions `live` and `comments` on the `jira` verb. `jira live [--jql] [--limit]` (default
  `jira_live_jql`, else `project = HWL ORDER BY updated DESC`; limit 2000, `truncated: true`
  plus a warning when cut, `limit must be at least 1` below 1) returns `jql`, `fetched_at`,
  `count`, `truncated`, `issues` (the sixteen `LIVE_FIELDS` per row) and publishes `jira.live`
  (`jql`, `count`, `truncated`, `fetched_at`, `actor`); no row and no audit entry is written.
  `jira comments <key>` returns the history newest first (`id`, `author`, `created`, `updated`,
  `body`) with `key`, `summary`, `url`, `status`, `fetched_at`, `count`, and publishes nothing.
- `JiraService.live_jql`, `live`, `comments`; `live_row`, `comment_row`, `LIVE_JQL`,
  `LIVE_LIMIT`, `LIVE_FIELDS` in `services/jira_service.py`. `live` asks Hopper for `limit + 1`
  rows so the extra one is the truncation signal.
- `dewey.toml` keys `jira_live_jql` (text) and `jira_live_autofetch` (a real TOML boolean,
  default `true`; `BOOL_CONFIG_KEYS` in `brain.py` ignores a string).
- `MainWindow.jira_live` (the session's fetch, kept across theme rebuilds),
  `MainWindow.comment_windows`, `open_comments(key)`, and `run_quiet` (`run` without the dialog;
  both share `_execute`).
- Tests: live and comments cases on the replay fixtures and on stubs in `tests/test_jira.py`,
  the screen and the comments window from a stubbed `run_quiet` in `tests/test_gui.py`, the two
  config keys in `tests/test_core.py`. `conftest.py` now points asi_hopper at an empty replay
  directory for every test, so no test can reach Jira.

### Changed
- The dashboard's `JIRA TICKETS` tile opens the `jira_live` screen (`TILE_TARGETS` in
  `gui/dashboard.py`); its count is still the cache's. The "Open Jira tickets" table is unchanged.
- `_on_event` ignores `jira.live` as it ignores `theme.changed`: no row changed, no screen is
  refreshed. `set_theme` clears `comment_windows` (the Toplevels are destroyed with the rest).
- Version 0.5.0. Schema version unchanged (1), no migration; `sync`, `status`, `get` and the
  `jira_ticket` cache are untouched.

## [0.4.0] - 2026-10-27

Fewer windows. The Safety Plan is edited in asi_kletz; the live Jira view is 0.5.0. See
`docs/prune-windows-plan.md`.

### Removed
- The `JIRA` screen (`entity:jira_ticket`), the `Safety Plan` screen (`entity:safety_plan_row`)
  and the `Safety Plan Matrix` screen (`safety_plan_matrix`) from the navigation list and the
  View menu. `show()` on any of the three keys raises `NotFound` like any unknown screen.
- `gui/matrix_screen.py` (`SafetyPlanMatrixScreen`).

### Changed
- `build_default_screens(brain, hidden=HIDDEN_ENTITY_SCREENS)` skips the entities named in
  `HIDDEN_ENTITY_SCREENS` (`gui/screens.py`: `jira_ticket`, `safety_plan_row`); a name that is
  not a registered entity is a `ValueError` at build time. Ten screens in nav order: Dashboard,
  the seven entity screens, Export / Import, Generate.
- Dashboard tiles whose entity has no screen keep their count but get no click or hover
  binding; the "Open Jira tickets" table is unchanged.
- Tests: `test_navigation_and_dashboard` asserts the exact nav order;
  `test_safety_plan_form_has_groups` and `test_matrix_toggle_and_group_switch` are deleted with
  their screens; `test_pruned_screens_are_absent` and
  `test_hidden_set_must_name_registered_entities` are new.
- Version 0.4.0. The entities, tables, workbook sheets, `dump` / `load`, the `jira` verb and
  the diagram and document catalogs are untouched; schema version unchanged (1), no migration.

## [0.3.0] - 2026-10-27

The family palette and a latching theme picker. See `docs/theme-palette-plan.md`.

### Added
- `gui/palettes.py`: the family palette, 32 palettes as pure data (8 hue families x 4 tones:
  cyan, blue, violet, pink, red, amber, gold, green; noir, neon, dusk, day), byte-identical in
  every ASI primary tool. The authority is the section "The family palette" in `ASI_FAMILY.md`;
  a test hashes the catalog and compares it with the digest written there
  (`befcfc0c8dca5479620badf1d23e2448db757910`), so a hand edit in one tool fails until the
  family file and the sibling agree. Contrast floors (WCAG 2) are tested on every palette.
- `GridTheme`: the dark/light grid recipe with the palette as a class attribute; one subclass
  per catalog entry is registered at import time. `ThemeFactory.alias()`, `entries()`
  (catalog order, no aliases), `resolve()` (argument, then `$ASI_DEWEY_THEME`, then the
  latched preference, then the house default) and `latched()`.
- `prefs.py`: `prefs_path()`, `read_prefs()`, `write_prefs(**changes)`, `ENV_PREFS`
  (`ASI_DEWEY_PREFS`). One flat JSON object at `%LOCALAPPDATA%\asi\dewey\prefs.json`
  (XDG state folder elsewhere), written atomically; a missing or corrupt file reads as `{}`.
- Verb `theme [key] [--list]`: no key lists the catalog, the latched key, the resolved key
  and the prefs path; a key validates it, writes the preference and publishes
  `theme.changed` (`theme`, `actor`); an unknown key is a `Result.failure`, exit 1.
- The window: a read-only `THEME` combobox at the foot of the navigation column and a
  `View > Theme` cascade (eight family submenus with four radio items each, then
  `Plain (native)`), both driving `MainWindow.pick_theme(key)`. `set_theme(key)` repaints by
  rebuilding the menu, body and status bar, so every tk widget, stripe tag and banner picks
  up the new palette; the open screen is kept; a screen exposing `is_dirty()` is asked first.
  `theme.changed` from any actor repaints an open window in this process. An unknown latched
  key opens the house default with a warning in the status bar.
- `tests/test_theme.py` (catalog, digest, contrast, factory, resolution, prefs); picker,
  repaint, latch and event cases in `tests/test_gui.py`; the verb in `tests/test_cli.py`.
  `tests/conftest.py` points `ASI_DEWEY_PREFS` at `tmp_path` and clears `ASI_DEWEY_THEME`.
- A bare boolean flag on the CLI (`--list`, `--dry-run`) now means true; `--flag false` still works.
- Jira, read only, through the sibling `asi-hopper` (editable uv path source, like the
  generators). `jira sync [--jql ...] [--dry-run true]` pulls the configured JQL into
  `jira_ticket`, upserting by issue key through the ordinary entity path (validation, audit as
  `jira:sync`, `jira.synced` event); rows whose key the JQL no longer returns are reported as
  stale, never deleted; hand-typed rows without a key are untouched; `order` is left to the
  engineer. `jira status` reports rows, counts by status, the last sync and the asi_hopper
  session; `jira get <key>` shows one live issue and the row it maps to. A missing Atlassian
  session is a `Result.failure` saying to run `asi-hopper auth login`.
- `jira_ticket` gains optional columns `key`, `issue_type`, `priority`, `assignee`,
  `parent_key`, `labels`, `updated`, `synced_at` (group `sync`; existing databases are migrated
  in place, the workbook sheet gains the columns). Jira status category maps to the
  `jira_status` lookup (`new → open`, `indeterminate → in progress`, `done → done`); `blocked`
  only when Jira's own status says Blocked.
- `jira_jql` in `dewey.toml` (a text key, not a path).
- `tests/test_jira.py` runs the verb against asi_hopper's recorded fixtures: no network, no
  session; skipped when asi_hopper is not checked out next to asi_dewey.

### Changed
- The house default theme is `cyan-neon`, which is the former `tron` palette under its family
  name; `tron` stays registered as an alias (`--theme tron`, `ASI_DEWEY_THEME=tron` keep
  working) and is listed once in the picker, as "Cyan Neon". `TronTheme` is now a name for
  the `cyan-neon` class.
- `Theme.apply` is re-entrant: it records the platform ttk theme, named fonts and root
  background on the first call, and every call starts from `option_clear()` and those
  defaults; `plain` restores the platform ttk theme, a `GridTheme` selects `clam`.
- `Treeview` selected foreground is `palette.text` instead of the literal `#ffffff`, so the
  light `day` tones stay legible. No literal colour is left in `theme.py`.
- `--theme` on `asi-dewey-gui` and on the `gui` verb passes through `ThemeFactory.resolve`;
  it is a one-off view and never writes the preference.

## [0.2.0] - 2026-10-27

Diagrams and documents. Dewey now uses both family generators through its own command path.

### Added
- Dependencies on the sibling generators `asi-escher` and `asi-gutenberg` as editable uv path
  sources (both declared in Dewey's own `pyproject.toml`); matplotlib, Pillow, reportlab and
  python-docx arrive transitively and are imported lazily, so `import asi_dewey` and window
  start-up stay as light as before (a test checks it).
- `asi_dewey.generate`: `Spec`, `Param`, `DiagramFactory`, `DocumentFactory`,
  `register_diagram`, `register_document`, and `figures.py` (the one place `asi_escher.build`
  is called: `LayoutWarning` captured, `LayoutIssue` objects turned into plain dicts).
- Diagram catalog: `schema_map`, `lifecycle_overview`, `phase_flow` (param `phase`),
  `task_flow` (param `class`).
- Document catalog: `safety_plan` (a working copy, no document id; the controlled plan is
  asi_kletz's), `status_report`, `handbook`. Figures are asi_gutenberg 0.2.0 `diagram` blocks
  rendered into `<out>/figures/`; metadata from the database (`Product` fact), author = the
  actor, status Draft.
- Verbs `diagram [name] [--out] [--formats] [--param k=v] [--dpi]` and
  `document [name] [--out] [--param k=v]`: no name lists the catalog; results carry `paths`,
  `primary`, `issues` (also as warnings), and for documents `pages`, `stats`, `diagrams`;
  unknown names and bad params are `Result.failure`; a locked PDF falls back to a timestamped
  stem; every build is audited (`generate`) and published as a `generated` event.
- Output folder: `out` in `dewey.toml`, `ASI_DEWEY_OUT`, `Brain(out_dir=...)`, default `out/`
  next to the database; `status` reports `out_dir`.
- Generate screen (output folder, both catalogs, a parameter form generated from the spec,
  Build / Open file / Open folder, result log) and File > Build document…. The screen calls
  only the two verbs. `os.startfile` is guarded: elsewhere the path is logged.
- `services/queries.py`: open Jira tickets, tasks due, recent changes, shared by the dashboard
  and the status report.
- Tests for the catalogs, every diagram and document, param validation, warning capture, the
  locked-PDF fallback, audit and events, out-dir precedence, the CLI, the Generate screen, and
  the lazy-import guarantee. The suite is isolated from `ASI_DEWEY_OUT` too.

### Changed
- The dashboard reads its three lists through `services/queries.py`.
- Long lines wrapped so `ruff check src tests` is clean.
- Version 0.2.0. Schema version unchanged (1); no migration.

## [0.1.0] - 2026-10-27

The screens. Everything in the window goes through the same command path as the CLI.

### Added
- `asi_dewey.gui`: `MainWindow` (navigation list, status bar, File/View/Help menus, Ctrl+N,
  Ctrl+S, Ctrl+E, Ctrl+Q, F5), `ScreenFactory`, `WidgetFactory` (entry, multiline, checkbox,
  date with Today, URL with Open, editable lookup combobox), and `ScrollableFrame`.
- Dashboard screen: row-count tiles that open the entity, open Jira tickets, tasks ending
  within seven days, recent audit entries.
- Generic `EntityScreen` for every registered entity: sortable, searchable table; form built
  from the schema with flag groups rendered as checkbox grids; New / Save / Delete /
  Duplicate / Refresh; validation errors and lookup warnings surfaced in the status bar.
- Safety Plan Matrix screen: deliverables as rows, one flag group as columns, click a cell to
  toggle it (location, reference, author, verification, reviewer).
- Export / Import screen: workbook export and import with mode, JSON dump and load, result log.
- Event-driven refresh: the open screen refreshes after any command, from any actor.
- `gui` verb (`asi-dewey gui [--theme tron|plain]`) and `asi-dewey-gui` console script.
- Themes: `Theme`, `TronTheme`, `ThemeFactory` (`ASI_DEWEY_THEME`). `tron` is the default:
  dark panels, cyan light lines, orange for the active element, geometric headings, monospace
  status line, striped tables, a grid banner on the dashboard. `plain` is the native look.
- GUI test suite driving real widgets with the window withdrawn.

### Fixed
- A refresh scheduled by the event bus could fire after the window was destroyed; `close`
  now cancels it.
- pytest runs with `--capture=sys`: under fd capture a destroyed Tcl interpreter could close
  a recycled handle and the next `Tk()` failed to read its own library files at random.

### Changed
- Renamed to **asi_dewey**, a sister project of asi_gutenberg and asi_escher: package
  `asi_dewey` in a `src` layout, commands `asi-dewey` and `asi-dewey-gui`, environment
  variables `ASI_DEWEY_*`, default files `dewey.db` and `dewey.xlsx`. No person is named
  anywhere in the tool.
- `dewey.toml` (git-ignored; `dewey.example.toml` as a template) sets the database and
  workbook paths, relative to the file, so the workbook can be generated into another folder.
  `status` reports `config_path`.
- Tests are isolated from the developer's `dewey.toml` and environment.
- Built and locked with uv; ruff configuration.
- Version 0.1.0.

## [0.0.0] - 2026-10-27

First alpha. Core only, no screens.

### Added
- Schema layer: `FieldSpec`, `FieldType` (text, multiline, int, bool, date, url, enum),
  `EntitySchema`, `SchemaRegistry`, soft `LookupRegistry`, and `flag_fields` for matrix columns.
- Nine built-in entities seeded from the workbook sheets: task, fact, machine_function,
  use_case, link, jira_ticket, qms_document, person, safety_plan_row (63 columns).
- Lookups: task_class, link_class, jira_status, pdp_phase, lifecycle_phase, plan_status.
- SQLite storage generated from the registry, with column auto-migration, a
  `schema_migrations` fingerprint table, and an `audit_log` (actor, action, entity, payload).
- Generic `SqlRepository` (get, list with filters/ordering/paging, count, create, update,
  delete, bulk insert) and `RepositoryFactory`.
- `EntityService` with validation, audit, events, and bulk `load_rows` in replace/merge/append modes.
- Command layer: `Result`, `Argument`, `Command`, `CommandFactory`, `Dispatcher`, and the
  verbs list, count, get, create, update, delete, schema, status, dump, load, export, import, run.
- JSON exporter/importer (single-entity and combined envelopes) and Excel exporter/importer
  (header-driven column mapping, repeated headers handled, locked-file fallback).
- `Brain` facade (`execute`, `execute_dict`, `service`, `status`), `EventBus`, `.jsonl` script runner.
- CLI `asi-dewey` built from command signatures; prints a JSON `Result`; exit code 1 on failure.
- pytest suite covering schema coercion, CRUD, audit, events, transfer round trips, and the CLI.
- README and this changelog.

[Unreleased]: https://example.invalid/asi-dewey/compare/v0.7.3...HEAD
[0.7.3]: https://example.invalid/asi-dewey/compare/v0.7.2...v0.7.3
[0.7.2]: https://example.invalid/asi-dewey/compare/v0.7.1...v0.7.2
[0.7.1]: https://example.invalid/asi-dewey/compare/v0.7.0...v0.7.1
[0.7.0]: https://example.invalid/asi-dewey/compare/v0.6.0...v0.7.0
[0.6.0]: https://example.invalid/asi-dewey/compare/v0.5.0...v0.6.0
[0.5.0]: https://example.invalid/asi-dewey/compare/v0.4.0...v0.5.0
[0.4.0]: https://example.invalid/asi-dewey/compare/v0.3.0...v0.4.0
[0.3.0]: https://example.invalid/asi-dewey/compare/v0.2.0...v0.3.0
[0.2.0]: https://example.invalid/asi-dewey/compare/v0.1.0...v0.2.0
[0.1.0]: https://example.invalid/asi-dewey/compare/v0.0.0...v0.1.0
[0.0.0]: https://example.invalid/asi-dewey/releases/tag/v0.0.0
