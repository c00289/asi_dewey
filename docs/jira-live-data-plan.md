# ASI Dewey — Plan: the JIRA Live Data window

**Status:** Implemented 2026-10-27 (asi_dewey 0.5.0); deviations recorded by the implementing agent in the CHANGELOG entry.
0.7.3 (2026-10-28) moved the fetch off the Tk thread and flipped `jira_live_autofetch` to `false`; see §8.
**Removed from the Dewey window in 0.8.1** (owner's instruction, 2026-10-28): the screen, the comments window
and `jira_live_autofetch` are gone; `jira live`, `jira comments` and the row convention of §3.1 stay, and
asi_kletz keeps its window. See `CHANGELOG.md`, section [0.8.1].
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_dewey 0.5.0 (after the 0.4.0 window prune, before the family lock at 0.6.0)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md); this plan adds a short table "The JIRA Live
Data window" there.
**Sister plan:** [asi_kletz/docs/jira-live-data-plan.md](../../asi_kletz/docs/jira-live-data-plan.md).
Same window convention, implemented twice, never shared as code.

---

## 1. The ask

Asked by the owner on 2026-10-27, verbatim: "a brand new window common to both tools right below
the dashboard called JIRA Live Data with only a refresh button and a big beautiful table of all
issues past and present with their status and include filtering by common sense fields".

Read as six decisions (the sixth added by the owner after reviewing the first draft):

1. **A new window, common to both tools.** Dewey and Kletz get the same screen under the same
   key, title, verb, columns and filters, so what the owner learns in one tool holds in the other.
   Common means the same convention, implemented twice; never a shared package.
2. **Right below the dashboard.** The screen is the second entry in the navigation list and in
   `View`, in both tools.
3. **Only a refresh button.** One action. No edit, no sync into the database, no timer. The
   window shows Jira; it never changes Jira and never stores what it shows.
4. **A big beautiful table of all issues past and present with their status.** The whole
   project, closed issues included, with status and status category visible, sortable on any
   column, striped, done rows dimmed, the summary column taking the room that is left.
5. **Filtering by common sense fields.** A text box on key and summary, and drop-downs for
   Status, Category, Type, Priority and Assignee, applied locally to the last fetch so a filter
   never costs a Jira call.
6. **A Comments button on every row, and a comments view.** Added by the owner on 2026-10-27
   after the first review: "include a column with a clickable button in the table for each line
   item where every line item is a jira ticket, and if you click on comment, which is the
   clickable comment button, then you get a subsidiary screen that shows the comments history
   with newest at the top and oldest at the bottom." The button is a cell of the table, the
   subsidiary screen is a window of its own per ticket, and it is fed by a verb like everything
   else (section 3.10).

Dewey keeps its existing Jira side as it is: `jira sync` still caches issues into the
`jira_ticket` table, `jira status` and `jira get` still answer, and the dashboard tile "Open Jira
tickets" still reads the cache. The live window is a different thing: a view over Jira held in
memory, never written to the database. After the 0.4.0 prune removes the `entity:jira_ticket`
screen this is Dewey's only Jira window; the cached table stays reachable through the verbs, the
workbook sheet and the dashboard tile.

## 2. What exists today (verified 2026-10-27)

| Fact | Where |
|---|---|
| `JiraCommand`, verb `jira`, `Argument("action", choices=("sync", "status", "get"))`, flags `--jql` (default "jira_jql in dewey.toml, else DEFAULT_JQL") and `--dry-run` (bool). `sync` returns the service summary and turns `stale` into a `Result` warning. | `commands/jira.py` |
| `JiraService` is `brain.jira`. `jql(override)` is override, else `config["jira_jql"]`, else `DEFAULT_JQL` (open issues assigned to or watched by the current user). `open_hopper()` imports `asi_hopper` lazily and returns `Hopper(interactive=False)`; an `ImportError` becomes `CommandError(INSTALL_HINT)`. `_fetch` calls `hopper.search(jql)` (all pages, no limit) and closes a Hopper it opened itself. `_guard` maps `AuthRequired` to `CommandError(str(exc))` and any other `HopperError` to `CommandError("Jira read failed: ...")`. | `services/jira_service.py` |
| `sync` writes through `EntityService` (actor `hopper` by default), audits `jira:sync`, publishes `jira.synced`. `map_record` produces the `jira_ticket` columns: `name` from the summary, `status` mapped to the `jira_status` lookup, labels joined with `;`. `get` returns `{"issue": record.to_dict(), "row": map_record(record)}`. | `services/jira_service.py` |
| `Dispatcher.execute` turns `BrainError` (so `CommandError`) and `ValueError` into `Result.failure`; any other exception is logged and becomes `Result.failure("<Type>: <message>")`. No exception reaches the window. | `commands/dispatcher.py`, `errors.py` |
| The CLI types arguments through `_TYPES = {"str", "path", "int", "json", "kv", "bool"}`, so an `Argument(type="int")` is parsed as an integer. | `automation/cli.py` |
| `MainWindow.run(verb, **args)` calls `brain.execute(verb, args, actor="gui")`; a failure goes to `notify_error` (status bar `Error: ...` plus a dialog when `interactive`); warnings go to the status bar as `Warning: ...`. | `gui/main_window.py` |
| `_on_event`: `theme.changed` repaints the window; every other topic schedules `current.refresh()` after 50 ms, coalesced through `_refresh_job`. F5 calls `current.refresh()`. `set_theme` destroys every child, clears `_screens`, rebuilds menu and body, and shows the previous key again: a screen's own state does not survive a theme pick. | `gui/main_window.py` |
| The navigation `Listbox` and the `View` menu are built from `factory.items()` in registration order; `show(key)` creates a screen on first use and calls `on_show()`, whose default is `refresh()`. | `gui/main_window.py`, `gui/screens.py` |
| `build_default_screens` registers `dashboard`, then `entity:<name>` for every schema in the registry, then `safety_plan_matrix` (removed in 0.4.0), `transfer`, `generate`. | `gui/screens.py` |
| The dashboard table "Open Jira tickets" reads `open_jira_tickets(brain)`, the `jira_ticket` rows with status `open`: the cache, never a live call. | `gui/dashboard.py`, `services/queries.py` |
| `Theme.stripe(tree)` configures the `odd` and `even` tags and **replaces** each item's tag tuple. `Palette` has a `muted` slot; `Muted.TLabel` is styled with it; `Treeview` selected foreground is `palette.text`. `theme.ui` and `theme.mono` are the two font tuples. | `gui/theme.py` |
| `EntityScreen` is the house table: a `Treeview` with both scrollbars in a grid, heading click to `sort_by(column)` (toggles direction on the same column), `search_var.trace_add("write", ...)` to repopulate on every keystroke, a `count_var` label at the right of the toolbar, `cell_text` truncating at 70 characters. `UrlWidget.open` uses `webbrowser.open`. The Generate screen logs a path instead of opening it when the window is not interactive. | `gui/entity_screen.py`, `gui/widgets.py`, `gui/generate_screen.py` |
| `tests/test_jira.py` runs the verb against the replay gateway: an autouse fixture deletes `ASI_HOPPER_CONFIG` and sets `ASI_HOPPER_GATEWAY=replay`, `ASI_HOPPER_FIXTURES=<asi_hopper>/tests/fixtures`; the module is skipped when the fixtures are not checked out next to the repo. `OPEN_JQL` returns three issues: HWL-2572, HWL-2575, HWL-2620. | `tests/test_jira.py` |
| `tests/test_gui.py` opens real `MainWindow`s (skipped without a display), asserts `keys[0] == "dashboard"`, and polls `window.update()` for up to 2 s when an event should refresh a screen. | `tests/test_gui.py` |
| `asi-hopper` is an editable path dependency (`../asi_hopper`). `dewey.example.toml` documents `jira_jql`; `load_config` reads path keys and `TEXT_CONFIG_KEYS = ("jira_jql",)` and nothing else (no boolean keys yet). | `pyproject.toml`, `dewey.example.toml`, `brain.py` |
| Hopper: `Hopper.search(jql, *, fields=None, all_pages=True, limit=None)` calls `IssueService.search(max_results=100, ...)`; with `limit`, it returns `records[:limit]` as soon as `len(records) >= limit`, so exactly `limit` rows cannot be told from more than `limit`; `MAX_PAGES = 200`. `IssueRecord` carries key, id, project, project_name, issue_type, summary, status, status_category, resolution, priority, assignee, assignee_id, reporter, reporter_id, labels, components, parent (`IssueRef`), created, updated, due, url, description, links, comments, custom, raw. `to_row()` names the type `type` and the parent `parent` and joins labels with `;`. `AuthRequired` and `NotRecorded` are `GatewayError`s, which are `HopperError`s. | `../asi_hopper/src/asi_hopper/hopper.py`, `services/issues.py`, `model/records.py`, `errors.py` |
| Replay matching: `canonical_args` drops `cloudId` and `None` values; a search call is `{jql, fields (the 16 defaults), maxResults 100, responseContentFormat "markdown"}`; `limit` and `all_pages` never reach the gateway. `index.json` **does** list `searchJiraIssuesUsingJql` for `OPEN_JQL` at `maxResults` 50 and 100, file `searchJiraIssuesUsingJql_open.json`, three issues, `pageInfo.hasNextPage` false. There is no fixture for the house default JQL of this plan. | `../asi_hopper/tests/fixtures/index.json`, `gateway/replay.py`, `gateway/base.py`, `gateway/api.py` |
| The older integration plan describes dewey's `jira sync/status/get`, the schema columns, the dashboard tile and a "Sync Jira" button (all implemented but the button, which the 0.4.0 prune makes moot) and kletz's `jira reconcile` / `jira link` (not implemented). | `../asi_hopper/docs/integration-plan.md` |
| `Comment` is a frozen dataclass: `id, author, author_id, created, updated, body`. `IssueRecord.comments` is filled only when the call asks for the `comment` field: `JiraApi.get_issue(key, comments=True)` appends `comment` to the 16 defaults; `search` never asks, so a search row's `comments` is `()` and no comment count exists without a per-issue call. Bodies arrive as Markdown (`responseContentFormat: "markdown"`) or as ADF that `adf_to_markdown` renders to Markdown; either way `body` is a Markdown string. | `../asi_hopper/src/asi_hopper/model/records.py`, `model/normalise.py`, `adf/convert.py`, `gateway/api.py` |
| `index.json` lists `getJiraIssue` for HWL-2575 with the 16 defaults plus `comment`, so `hopper.get("HWL-2575", comments=True)` replays; that file's `comment` block is `{"comments": [], "total": 0}`: the path is recorded, the history is empty. | `../asi_hopper/tests/fixtures/index.json`, `getJiraIssue_HWL-2575.json` |
| `Theme.paint` sets `root.configure(background=p.bg)` and option-database defaults for `Listbox`, `Text`, `Canvas`, `Menu` and the combobox list only; nothing for `Toplevel` or `Frame`. A `tk.Toplevel` whose master is the root is in `root.winfo_children()`, so the `set_theme` loop destroys it with the rest. `ScrollableFrame` (canvas, inner frame, wheel binding) lives in `gui/screens.py`. | `gui/theme.py`, `gui/main_window.py`, `gui/screens.py` |
| `ttk.Treeview` tags style items (whole rows), never single cells; `identify_column(x)` and `identify_row(y)` map a click to a cell. Windows in the test suite are `withdraw()`n and never mapped, so `bbox` and `identify_*` return empty there. | Tk `ttk::treeview` manual; `tests/test_gui.py` |
| The family document (now `ASI_FUSA_TOOLS.md`) has the version table, the plans table and the palette section with its `| Item | Convention |` table. When this was verified the version table still said 0.2.0 for both primary tools and listed `asi_hopper` without a version (it is 0.1.1 today), and the plans table had five rows with the lock plans targeted at 0.3.0 (they shipped as 0.6.0). | `../asi_fusa_tools/ASI_FUSA_TOOLS.md` |
| `docs/prune-windows-plan.md` (0.4.0, draft) hides the Jira and both Safety Plan screens, leaving ten in nav order (dashboard, task, fact, machine_function, use_case, link, qms_document, person, transfer, generate), makes a dashboard tile whose entity has no screen non-clickable, keeps the "Open Jira tickets" table, and leaves to this plan "whether the `jira_ticket` tile should open the `jira_live` screen". `docs/single-instance-plan.md` is re-targeted to 0.6.0; `docs/automation-server-plan.md` (0.7.0, draft) does not mention this window. | `docs/prune-windows-plan.md`, `docs/single-instance-plan.md`, `docs/automation-server-plan.md` |

## 3. Design

### 3.1 The convention (the same in both tools)

| Item | Convention |
|---|---|
| Screen | key `jira_live`, title `JIRA Live Data`, module `gui/jira_live_screen.py`, class `JiraLiveScreen`, registered immediately after `dashboard` |
| Verbs | `jira live [--jql <jql>] [--limit <n>]` and `jira comments <key>`; the windows never call Hopper themselves |
| JQL default | `--jql`, else `jira_live_jql` in `<tool>.toml`, else `project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC` ("all issues past and present") |
| Limit default | 2000; a longer result is cut and reported as a `Result` warning with `truncated: true` |
| toml keys | `jira_live_jql` (text), `jira_live_autofetch` (bool, default `false` since 0.7.3; `true` in 0.5.0) |
| Columns | Comments (the per-row button), Key, Type, Summary, Status, Category, Priority, Assignee, Reporter, Labels, Parent, Created, Updated, Due, Resolution |
| Filters | text on key or summary; Status, Category, Type, Priority, Assignee; all local, never a re-query |
| Comments view | `gui/jira_comments_window.py`, `JiraCommentsWindow(tk.Toplevel)`, one per ticket, title `<KEY> — Comments`, newest first, fed by `jira comments` |
| Event | `jira.live` with `jql`, `count`, `truncated`, `fetched_at`, `actor`; `jira comments` publishes nothing; neither writes the database or the audit log |
| Storage | none: the last fetch lives on the window object for the life of the process |

The authority is the table "The JIRA Live Data window" that phase 5 adds to the family
document. Each tool carries its own copy of the verb, the service method and the screen; the
agreement is the convention and this plan, never an import.

### 3.2 The `jira live` action

`live` joins `sync`, `status` and `get` on the existing verb:

```
asi-dewey jira live                                       # house JQL or jira_live_jql, limit 2000
asi-dewey jira live --jql "project = HWL AND type = Bug"  # one-off JQL
asi-dewey jira live --limit 300                           # cap the fetch; truncated is reported
asi-dewey --compact jira live | jq '.data.issues[] | .key'
```

`commands/jira.py`: `choices=("sync", "status", "get", "live")`; `--jql` keeps its flag and its
help gains "for `live`: default `jira_live_jql`, else the house JQL"; new
`Argument("limit", "For `live`: most issues to fetch (default 2000)", flag=True, type="int", default=LIVE_LIMIT)`.
The `live` branch is three lines: call `jira.live(args.get("jql"), int(args.get("limit") or LIVE_LIMIT))`,
publish the event, return `Result.success(data, warnings)` where the one possible warning is
`fetch truncated at <limit> issues; narrow the JQL or raise --limit`.

Result data:

```json
{"jql": "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC",
 "fetched_at": "2026-10-27T18:04:11+00:00",
 "count": 2,
 "truncated": false,
 "issues": [
   {"key": "HWL-2572", "issue_type": "Story",
    "summary": "STPA Step 1 – Losses, Hazards & System Boundary – Peer Review",
    "status": "In Progress", "status_category": "indeterminate", "resolution": null,
    "priority": "Un-Groomed", "assignee": "...", "reporter": "...",
    "labels": [], "components": [], "parent_key": "HWL-1915",
    "created": "2026-10-20T09:12:40.000-0600", "updated": "2026-10-27T11:18:59.416-0600",
    "due": null, "url": "https://asirobots.atlassian.net/browse/HWL-2572"},
   "..."]}
```

Every row value is a string or `null` except `labels` and `components`, which are lists (possibly
empty). Dates and times are passed through as Jira returns them; the screen shortens them for
display, the Result does not. `fetched_at` is UTC ISO 8601 to the second, the same format the
event bus stamps on `ts`.

Failures, all `Result.failure` with exit code 1 on the CLI:

| Condition | Message |
|---|---|
| `asi_hopper` not importable | `asi_hopper is not installed: run `uv add --editable ../asi_hopper` in asi_dewey` (the existing `INSTALL_HINT`) |
| no Atlassian session (`AuthRequired`) | Hopper's own text: `no Atlassian session for this account; run `asi-hopper auth login` once` |
| any other `HopperError` (network, server, unrecorded fixture) | `Jira read failed: <hopper message>` |
| `--limit` below 1 | `limit must be at least 1` |

After the fetch the command publishes
`ctx.brain.events.publish("jira.live", jql=jql, count=n, truncated=bool, fetched_at=ts, actor=ctx.actor)`.
Nothing is audited: the audit log records changes to the database and a read is not one; the
event is the trace, and it shows in `status()["recent_events"]`.

### 3.3 `JiraService.live`

`services/jira_service.py` gains two constants, one mapping function and one method; `sync`,
`get`, `status`, `map_record` and `map_status` are untouched.

```python
LIVE_JQL = "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC"
LIVE_LIMIT = 2000
LIVE_FIELDS = ("key", "issue_type", "summary", "status", "status_category", "resolution", "priority",
               "assignee", "reporter", "labels", "components", "parent_key", "created", "updated", "due", "url")


def live_row(record: Any) -> dict[str, Any]:
    """An asi_hopper IssueRecord -> the row of the JIRA Live Data convention (section 3.1)."""
    return {
        "key": record.key, "issue_type": record.issue_type, "summary": record.summary,
        "status": record.status, "status_category": record.status_category,
        "resolution": record.resolution, "priority": record.priority,
        "assignee": record.assignee, "reporter": record.reporter,
        "labels": list(record.labels), "components": list(record.components),
        "parent_key": record.parent.key if record.parent else None,
        "created": record.created, "updated": record.updated, "due": record.due, "url": record.url,
    }


class JiraService:
    def live_jql(self, override: str | None = None) -> str:
        return override or self.brain.config.get("jira_live_jql") or LIVE_JQL

    def live(self, jql: str | None = None, limit: int = LIVE_LIMIT, *, hopper: Any = None) -> dict[str, Any]:
        """Fetch ``jql`` live and return the convention's dict. Nothing is written anywhere."""
        if limit < 1:
            raise CommandError("limit must be at least 1")
        jql = self.live_jql(jql)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            records = self._guard(lambda: hopper.search(jql, all_pages=True, limit=limit + 1))
        finally:
            if own:
                hopper.close()
        issues = [live_row(r) for r in records[:limit]]
        return {
            "jql": jql,
            "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "count": len(issues),
            "truncated": len(records) > limit,
            "issues": issues,
        }
```

Why `live_row` and not `IssueRecord.to_row()`: the convention keeps `labels` and `components` as
lists, names the type `issue_type` and the parent `parent_key` (the same names as the
`jira_ticket` columns, so a reader of `jira get` and of `jira live` sees one vocabulary), and adds
`reporter`, `resolution` and `components`, which `to_row` lacks. `to_row` stays Hopper's CSV shape.

Why `limit + 1`: Hopper's `limit` returns exactly `limit` rows whether the query had `limit` or
`limit + 5000` matches. Asking for one more makes the extra row the signal: `truncated` is true
exactly when it arrives, and it is dropped. The cost is nothing (pages are 100 issues; `2001`
needs the same 21 calls as `2000`). With the default limit a full fetch is at most 21 calls, well
under Hopper's own `MAX_PAGES` ceiling of 200.

`hopper=` stays a keyword for tests and for a caller that already holds a Hopper, exactly as in
`sync` and `get`; the window never passes it.

### 3.4 Configuration

Two keys in `dewey.toml`, both optional:

```toml
# JQL the JIRA Live Data window and `asi-dewey jira live` fetch (default: every HWL issue, newest
# change first). Distinct from jira_jql, which is what `jira sync` caches into the Jira Ticket table.
jira_live_jql = "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC"

# Opt in to one fetch when the JIRA Live Data window is first shown in a session. Default false
# (since 0.7.3): the window never connects to Jira on its own and waits for Refresh.
jira_live_autofetch = false
```

`brain.py`: `TEXT_CONFIG_KEYS = ("jira_jql", "jira_live_jql")` and a new
`BOOL_CONFIG_KEYS = ("jira_live_autofetch",)` that `load_config` copies only when the TOML value is
a boolean (a string `"false"` is ignored with the key left absent, so the default applies; TOML
has a real boolean type and the example file shows it). Precedence for the JQL: `--jql`, then
`jira_live_jql`, then `LIVE_JQL`. Precedence for autofetch: the toml key, else `true`; there is no
argument and no environment variable, because it is a project habit, not a one-off. (0.7.3: the
default is `false`; the paragraph above described 0.5.0.) `jira_jql`
keeps its meaning and its default; the two keys answer different questions (what to cache, what
to look at).

### 3.5 The screen

`gui/jira_live_screen.py`, `class JiraLiveScreen(Screen)`, registered in `build_default_screens`
right after the dashboard:

```python
factory.register("dashboard", "Dashboard", DashboardScreen)
factory.register("jira_live", "JIRA Live Data", JiraLiveScreen)
for schema in brain.registry: ...
```

Navigation order after this plan (0.4.0 having removed the Jira and both Safety Plan screens):
Dashboard, JIRA Live Data, Tasks, Facts, Machine Functions, Use Cases, Links, QMS Documents,
People, Export / Import, Generate. The registration is positional, so the order is the same if
this lands before 0.4.0; only the entries after it differ.

**The `JIRA TICKETS` tile.** The prune plan left one question to this plan: after 0.4.0 the
`jira_ticket` entity has a count tile on the dashboard but no screen, so the tile is dead. Decided:
the tile opens `jira_live`. `gui/dashboard.py` gets a two-line map `TILE_TARGETS = {"jira_ticket":
"jira_live"}` and the tile loop binds the click to `TILE_TARGETS.get(schema.name, f"entity:{schema.name}")`
when that key is in the factory (the prune plan's guard, with the target looked up first). The
count on the tile stays the cache count; the window it opens is the one Jira window. The "Open
Jira tickets" table keeps reading the cache: it is the dashboard's job to show what `jira sync`
keeps, and the live screen is one click away.

Widget tree:

```
JiraLiveScreen (ttk.Frame, padding 8)
├── toolbar (ttk.Frame)                         pack x, pady (0, 6)
│   ├── Refresh (ttk.Button) -> fetch()         side left
│   └── status_var label (Muted.TLabel)         side left, padx 12: "n issues · fetched hh:mm · <jql>"
├── filter_row (ttk.Frame)                      pack x, pady (0, 6)
│   ├── "Find" label + Entry(filter_var, 28)    side left; key or summary, case-insensitive substring
│   ├── for field in (status, status_category, issue_type, priority, assignee):
│   │     caption label + Combobox(readonly, filters[field], width 16)   side left
│   ├── "Clear filters" (ttk.Button) -> clear_filters()                   side left, padx 8
│   └── count_var label (Muted.TLabel)          side right: "shown of count issues"
└── table (ttk.Frame)                           pack both, expand
    ├── tree (ttk.Treeview, show="headings", selectmode="browse", 15 columns, Comments first)  grid 0,0 nsew
    ├── ybar (ttk.Scrollbar vertical)           grid 0,1 ns
    └── xbar (ttk.Scrollbar horizontal)         grid 1,0 ew
```

Captions over the comboboxes are Status, Category, Type, Priority, Assignee. The combobox state
is `readonly` so a filter is always one of the listed values and never free text.

Columns, in order (`COLUMNS` in the module; the heading text is the convention's column name):

| Column id | Heading | Width | Stretch | Cell |
|---|---|---|---|---|
| `comments` | Comments | 90 | no | `[Comments]` on every row: the per-row button, section 3.10 |
| `key` | Key | 90 | no | as is |
| `issue_type` | Type | 90 | no | as is |
| `summary` | Summary | 420 | **yes** | truncated at 90 characters with `…` |
| `status` | Status | 130 | no | as is |
| `status_category` | Category | 110 | no | as is |
| `priority` | Priority | 100 | no | as is |
| `assignee` | Assignee | 150 | no | as is |
| `reporter` | Reporter | 150 | no | as is |
| `labels` | Labels | 160 | no | `", ".join(labels)` |
| `parent_key` | Parent | 90 | no | as is |
| `created` | Created | 100 | no | first 10 characters (`YYYY-MM-DD`) |
| `updated` | Updated | 100 | no | first 10 characters |
| `due` | Due | 100 | no | first 10 characters |
| `resolution` | Resolution | 110 | no | as is |

`None` shows as an empty cell. Each row's `iid` is its issue key, so a selection maps back to the
row dict without a lookup table.

**Sorting.** Every heading but Comments has `command=lambda c=column: self.sort_by(c)`; the same column
toggles ascending/descending, a new column starts ascending; the sorted heading carries a trailing
`▲` or `▼`. Sort values come from the row dict, not from the cell text, so dates sort on the full
timestamp and `key` sorts numerically: `("HWL", 2620)` after `("HWL", 999)`. `None` sorts last in
both directions. Default order is the server's (the JQL's `ORDER BY`), reached again by `Clear
filters`.

**Stripes and the muted tag.** After every fill: `self.window.theme.stripe(self.tree)`, then, for
each row whose `status_category == "done"`, `tree.item(iid, tags=(*tree.item(iid, "tags"), "muted"))`.
The order matters because `stripe` replaces the tag tuple. The screen configures
`tree.tag_configure("muted", foreground=self.window.theme.palette.muted)` once in `build`; the
stripe tags set only `background` and `muted` sets only `foreground`, so the two never compete and
a done row is dim on its stripe. The screen reads `self.window.theme` for both, like every other
screen, and because a theme pick rebuilds the screen it always reads the palette that is painting
the window.

**Opening an issue.** `<Double-1>` outside the Comments column and `<Return>` on the tree call
`open_selected()`: the focused row's `url` goes to `webbrowser.open` when the window is
interactive; when it is not (tests) the status bar shows `Open: <url>` instead, the Generate
screen's convention. A click in the Comments column and the `c` key open the comments view
(section 3.10).

**Read only.** No form, no edit, no context menu. The buttons that touch Jira are Refresh and the
`[Comments]` cells, and both only read.

### 3.6 Local filtering

`_populate()` runs on every keystroke in the text box (`filter_var.trace_add("write", ...)`), on
every `<<ComboboxSelected>>`, on `Clear filters`, on `sort_by`, and after a fetch. It never calls
the verb.

```
rows   = issues of the last good fetch (or [] when there is none)
needle = filter_var.get().strip().casefold()
if needle:
    rows = [r for r in rows if needle in (r["key"] or "").casefold()
                             or needle in (r["summary"] or "").casefold()]
for field, var in filters.items():                 # status, status_category, issue_type, priority, assignee
    choice = var.get()
    if choice == "(all)": continue
    want = None if choice == "(none)" else choice
    rows = [r for r in rows if r[field] == want]
rows = sorted(rows, key=sort_value, reverse=desc) if sort_column else rows
fill the tree, stripe, mute; count_var = f"{len(rows)} of {len(issues)} issues"
```

Combobox values are rebuilt after every fetch: `["(all)", *values]` where `values` are the
distinct non-null strings present, sorted case-insensitively, plus `(none)` at the end when any
row has `null` there. Category lists its values in the fixed order `new`, `indeterminate`, `done`
(only those present). A selection that is still present after a refetch is kept; one that is gone
resets to `(all)`. `Clear filters` sets the text box to `""`, every combobox to `(all)`, and the
sort to none.

### 3.7 Fetch, show, refresh, rebuild

**Where the last fetch lives: on the window object.** `MainWindow.__init__` sets
`self.jira_live: Result | None = None`. The screen keeps nothing of its own but widgets. Reasons:
`set_theme` destroys and recreates every screen, so a per-screen cache would make a theme pick
cost a Jira round trip and lose a 2000-row fetch; the window outlives screens and is the natural
"this session" scope the brief asks for ("does not auto-fetch on first show if a fetch already
happened this session"); and one attribute is enough because the Result carries everything the
screen needs, including the error text of a failed fetch.

**`fetch()`** (the Refresh button):

```python
def fetch(self) -> Result:
    self.window.set_status("Fetching Jira …")
    self.update_idletasks()
    result = self.window.run_quiet("jira", action="live")
    if result.ok or self.window.jira_live is None:
        self.window.jira_live = result          # a failure after a success keeps the old rows
    self.refresh()
    return result
```

`run_quiet` is `run` without the dialog: same `brain.execute(verb, args, actor="gui")`, same
`Error: ...` / `Warning: ...` lines in the status bar, no `messagebox`. It is a four-line sibling
of `run` in `MainWindow`, and `run` and `run_quiet` share one private `_execute`. The fetch goes
through the command path like every other window action, so the actor is `gui`, the `jira.live`
event is published, and an agent reading `status()["recent_events"]` sees that the window
fetched. A missing session on a machine without a browser session must never be a modal dialog
in the engineer's face on first show, which is why the live screen uses the quiet form for the
button too: the status bar is where this screen reports, every time.

**`refresh()`** repaints from `self.window.jira_live` and never fetches:

| `window.jira_live` | Toolbar status label | Table |
|---|---|---|
| `None` (never tried) | `No fetch yet · press Refresh` | empty |
| failed Result | `Offline: <first error> · press Refresh` | empty |
| ok Result | `{count} issues · fetched {hh:mm local} · {jql}`, plus ` · truncated at {limit}` when truncated | filled, filtered, sorted |

`fetched hh:mm` is `fetched_at` parsed and converted to local time. The status line is the
screen's own label; the window status bar is for errors, warnings and `Open:` lines.

**`on_show()`**:

```python
def on_show(self) -> None:
    if self.window.jira_live is None and self.brain.config.get("jira_live_autofetch", True):
        self.fetch()
    else:
        self.refresh()
```

First show in a session with autofetch on: one fetch. Any later show, a show after a failed
first fetch, or autofetch off: a repaint with the status line saying what the table holds. An
engineer offline sees an empty table, `Offline: no Atlassian session ...` in the toolbar label and
`Error: ...` in the status bar, and no dialog.

**Rebuild on a theme pick.** `set_theme` recreates the screen; `on_show` runs on the new
instance, finds `window.jira_live` set, and repaints from it. No refetch, and the muted tag
and stripes are configured again from the new palette. Filters and sort are reset by the rebuild
(the widgets are new); the rows are not.

**Event routing.** `_on_event` gains one line next to the `theme.changed` branch:
`if topic == "jira.live": return`. No database row changed, so no screen needs a refresh; the
screen that ran the verb has already painted its Result, and a dashboard or entity screen that
happens to be open must not re-read the database because somebody looked at Jira. `jira.synced`
keeps its current path (it does change rows). `theme.changed` and `jira.live` are then the two
topics the generic refresh ignores, and the docstring of `main_window.py` says so.

**F5.** The window's F5 still calls `current.refresh()`, which on this screen is the repaint.
Fetching is the button, as asked; whether F5 should also fetch is an open item.

### 3.8 Error handling, end to end

| Condition | Caught by | Result | Window |
|---|---|---|---|
| `asi_hopper` not installed | `open_hopper` → `CommandError(INSTALL_HINT)` | failure | status bar `Error: asi_hopper is not installed ...`; rows left as they were |
| No session (`AuthRequired`) | `_guard` | failure with Hopper's login hint | status bar `Error: no Atlassian session ...; run asi-hopper auth login once`; rows left |
| Network, server, unrecorded fixture (`HopperError`) | `_guard` → `Jira read failed: ...` | failure | same |
| Unexpected exception in Hopper or normalisation | `Dispatcher.execute` | failure `<Type>: <message>` | same |
| More than `limit` issues | `live` | success, `truncated: true`, one warning | rows shown; status bar `Warning: fetch truncated at 2000 issues; ...`; toolbar label ends `· truncated at 2000` |
| Empty result (JQL matches nothing) | — | success, `count: 0` | empty table; label `0 issues · fetched ...` |

### 3.9 What this plan takes from the older hopper integration plan

From `../asi_hopper/docs/integration-plan.md` this plan keeps the dependency pattern (section 1),
`Hopper(interactive=False)`, the `AuthRequired` wording rule (surface the login instruction,
nothing else), and the surface rule (`Hopper`, `IssueRecord`, the two error classes; nothing from
`asi_hopper.gateway`). It leaves for later, in that plan, dewey's "Sync Jira" button (moot after
the 0.4.0 prune), kletz's `jira reconcile` and `jira link`, and the evidence snapshots. Hopper
itself is not changed: `search` and `IssueRecord` already give everything the window needs.

### 3.10 Comments: the column, the verb, the window

**The column.** `comments` is the **first** column, before Key: with fourteen data columns the
last one sits behind the horizontal scrollbar at most window widths, and a button that has to be
scrolled to is not a button. Every cell reads `[Comments]`, nothing else: a count would need the
`comment` field, which search never fetches (section 2), and asking for it on every page would
drag every body of every issue through each fetch and change the recorded search call. The
heading has no sort command. The cursor becomes `hand2` while the pointer is over that column
(a `<Motion>` handler asking `identify_column`), which is the one per-cell visual Tk allows: a
Treeview tag styles the whole item, so an accent-foreground "link" tag would colour the entire
row and is not used. `<Button-1>` on the tree runs `_on_click`:

```python
def _on_click(self, event: tk.Event) -> str | None:
    if self.tree.identify_column(event.x) != "#1":
        return None                              # any other column: normal selection
    key = self.tree.identify_row(event.y)
    if key:
        self.window.open_comments(key)
    return "break"
```

`<Double-1>` keeps opening the URL except in that column; `<Return>` keeps opening the URL; `c`
on the tree opens the comments of the focused row. This is the Tk-native per-row button: the
widget has no cell widgets, so the cell is text and the click is routed by position.

**The verb.** `jira comments <key>`, a fifth action on the `jira` verb
(`choices=("sync", "status", "get", "live", "comments")`); the existing positional `key` serves
`get` and `comments` and its help says so. Result data:

```json
{"key": "HWL-2572", "summary": "STPA Step 1 – ...", "url": "https://.../browse/HWL-2572",
 "status": "In Progress", "fetched_at": "2026-10-27T18:04:11+00:00", "count": 2,
 "comments": [
   {"id": "10452", "author": "...", "created": "2026-10-26T15:02:11.000-0600",
    "updated": "2026-10-26T15:40:00.000-0600", "body": "Reviewed the loss list; L3 needs ..."},
   {"id": "10431", "author": "...", "created": "2026-10-21T09:12:40.000-0600",
    "updated": "2026-10-21T09:12:40.000-0600", "body": "Draft attached."}]}
```

Newest first by `created`, ties by `id`, both descending. Failures mirror `live`: `INSTALL_HINT`,
Hopper's `AuthRequired` text, `Jira read failed: <message>` for every other `HopperError`, which
includes an unknown key (`issue HWL-1 not found or not visible to this account`); a missing key
is `jira comments needs an issue key, e.g. HWL-2572`.

`JiraService.comments(key, *, hopper=None) -> dict`, beside `live` in `services/jira_service.py`:

```python
def comment_row(comment: Any) -> dict[str, Any]:
    return {"id": comment.id, "author": comment.author, "created": comment.created,
            "updated": comment.updated, "body": comment.body or ""}


def comments(self, key: str, *, hopper: Any = None) -> dict[str, Any]:
    key = (key or "").strip().upper()
    if not key:
        raise CommandError("jira comments needs an issue key, e.g. HWL-2572")
    own = hopper is None
    hopper = hopper or self.open_hopper()
    try:
        record = self._guard(lambda: hopper.get(key, comments=True))
    finally:
        if own:
            hopper.close()
    items = sorted((comment_row(c) for c in record.comments),
                   key=lambda c: (c["created"] or "", c["id"] or ""), reverse=True)
    return {"key": record.key, "summary": record.summary, "url": record.url, "status": record.status,
            "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "count": len(items), "comments": items}
```

`author_id` is dropped from the row; `author` (the display name Jira shows) is kept, because a
history without its authors is not a history.

**Publishing.** `jira comments` publishes nothing, and the rule that says so is the one that
makes `jira live` publish: a verb publishes when it changes something a front end holds. `sync`
changes rows, `theme` changes the paint, `live` changes the session's live table
(`window.jira_live`). A comments lookup changes nothing anyone holds; it is `jira get` with a
different shape, and `get` publishes nothing today. The window that asked gets its Result back
directly.

**The window.** `gui/jira_comments_window.py`, `class JiraCommentsWindow(tk.Toplevel)`, master
the main window, one per ticket, non-modal, title `<KEY> — Comments`, 640 x 520, resizable.
`Theme.paint` paints the root's background and the option database only (section 2), so the
window sets `self.configure(background=self.window.theme.palette.bg)` itself; its ttk children
take the styles and its `tk.Text` bodies take the `*Text.*` option entries, so nothing else is
painted by hand.

```
JiraCommentsWindow (tk.Toplevel)
├── header (ttk.Frame, padding (10, 8))
│   ├── "<KEY>  <summary>" (Title.TLabel)   and   "<status>" (Muted.TLabel)
│   └── url (TLabel, foreground palette.accent, cursor hand2, <Button-1> -> webbrowser.open)
├── toolbar (ttk.Frame)
│   ├── Refresh (ttk.Button) -> fetch()     Close (ttk.Button) -> close()
│   └── status_var label (Muted.TLabel): "n comments · fetched hh:mm" or "Error: ..."
└── body (ScrollableFrame from gui/screens.py), one block per comment, newest at the top:
    ├── meta (Muted.TLabel): "<author> · <created>" + " · edited <updated>" when updated != created
    ├── text (tk.Text, wrap word, state disabled after insert, height min(lines, 12), padx 6)
    └── rule (Rule.TFrame, height 1)
```

Bodies are `tk.Text`, not wrapped `Label`s: bodies are long, carry newlines and Markdown, and an
engineer copies lines out of them into a review; a `Label` is not selectable and its `wraplength`
is a fixed pixel width. `state="disabled"` after the insert makes it read-only; the `*Text.*`
option entries give it the field colours and the monospace font. Timestamps show as
`YYYY-MM-DD HH:MM` (the first 16 characters, `T` replaced by a space), no zone conversion: a
comment's time is Jira's. Empty history: one `Muted.TLabel` reading `No comments.`. `<Escape>`
closes, `<F5>` refreshes.

`fetch()` runs `self.window.run_quiet("jira", action="comments", key=self.key)`: a success rebuilds
the body and sets the status line; a failure sets `Error: <first error>` in the window's own
status line, leaves whatever was listed in place, and leaves the window open so the engineer can
sign in and press Refresh. `run_quiet` also writes the `Error:` line to the main status bar,
which is right: that bar is the one place every error of the tool lands. `open_comments(key)` on
`MainWindow` is the only place the window is constructed:

```python
def open_comments(self, key: str) -> JiraCommentsWindow:
    win = self.comment_windows.get(key)
    if win is not None and win.winfo_exists():
        win.lift()
        win.focus_set()
        return win
    win = self.comment_windows[key] = JiraCommentsWindow(self, key)
    win.fetch()
    return win
```

`self.comment_windows: dict[str, JiraCommentsWindow]` starts empty in `__init__`; the window's
`close()` pops its key and destroys it. All comment windows close with the main window
(`destroy()` on the root takes every Toplevel with it). On a theme pick they are **destroyed,
not repainted**: the `set_theme` loop over `winfo_children()` already destroys them because a
Toplevel is a child of the root, and `set_theme` clears `comment_windows` in the same breath.
Reason: it is the rebuild rule every screen follows, the content is one `jira comments` away,
and repainting a `tk.Text` and each label by hand is the per-widget repaint the theme plan
rejected.

Why a Toplevel and not a screen in the navigation column: a comments view belongs to one ticket,
several can be open side by side while the table is still in use, and the nav list is for the
tool's own screens, not for one row of one of them.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Verb + service | `LIVE_JQL`, `LIVE_LIMIT`, `live_row`, `JiraService.live_jql`, `JiraService.live`; `live` on the `jira` verb with `--limit`; `jira.live` event; `jira_live_jql` and `jira_live_autofetch` in `load_config`. | `tests/test_jira.py` live cases of section 6 pass on the replay gateway; `asi-dewey jira live --jql "<OPEN_JQL>"` prints 3 issues; existing `jira` tests unchanged. |
| 2. Screen | `gui/jira_live_screen.py`; registration after `dashboard`; `MainWindow.jira_live`, `run_quiet`, the `jira.live` early return in `_on_event`; the `jira_ticket` tile targets `jira_live`. | `tests/test_gui.py` live cases pass; manual check: open the window, JIRA Live Data is second in the nav and in View, Refresh fills the table, filters narrow it per keystroke, a done row is dim, double-click opens the browser, pick a theme and the rows are still there. |
| 3. Comments | `comment_row`, `JiraService.comments`; action `comments` on the verb; the `[Comments]` column, `_on_click`, the `hand2` cursor, the `c` key; `gui/jira_comments_window.py`; `MainWindow.comment_windows`, `open_comments`, the clearing in `set_theme`. | Comments cases of section 6 pass on replay, the stub and the window; manual check: click `[Comments]` on a ticket with a history, newest at the top, click it again and the same window comes to the front, pick a theme and the window closes, click again and it comes back. |
| 4. Docs | README section "JIRA Live Data" (window, verbs `live` and `comments`, the comments window) and the window list in "What is in"; CHANGELOG 0.5.0 entry; `docs/plan.md` sections 8, 10 and 12; `dewey.example.toml` keys; `version.py` and `pyproject.toml` 0.5.0. | `uv run pytest` and `uv run ruff check src tests` clean; README examples run. |
| 5. Family | `ASI_FUSA_TOOLS.md`: version table 0.5.0 for both tools, plans table rows for the two `jira-live-data-plan.md` files, and the one-table section "The JIRA Live Data window" (key, title, verbs, JQL default, toml keys, comments view), written once and shared with the Kletz plan's phase 5. | The sister's phase 5 finds the section present and adds nothing; `diff` of the two plans shows only the differences listed in section 1 of each. Tag left to the owner. |

## 5. Files touched

```
src/asi_dewey/services/jira_service.py     LIVE_JQL, LIVE_LIMIT, LIVE_FIELDS, live_row, comment_row, JiraService.live_jql, live, comments
src/asi_dewey/commands/jira.py             actions `live` and `comments`, --limit (int), help text, jira.live event
src/asi_dewey/brain.py                     TEXT_CONFIG_KEYS + jira_live_jql; BOOL_CONFIG_KEYS = (jira_live_autofetch,)
src/asi_dewey/gui/jira_live_screen.py      new: JiraLiveScreen (toolbar, filter row, 15-column table with the [Comments] column)
src/asi_dewey/gui/jira_comments_window.py  new: JiraCommentsWindow (one Toplevel per ticket, newest first)
src/asi_dewey/gui/screens.py               register jira_live right after dashboard
src/asi_dewey/gui/main_window.py           jira_live and comment_windows attributes, run_quiet (+ shared _execute), open_comments, jira.live early return, docstring
src/asi_dewey/gui/dashboard.py             TILE_TARGETS: the jira_ticket tile opens jira_live (the cache table is unchanged)
tests/test_jira.py                         live: replay, limit/truncated, default JQL unrecorded, config key, event, no write; comments: replay (empty history), stub ordering, unknown key
tests/test_gui.py                          nav order, fill from a stubbed run, sort, filters, muted, status, rebuild, no write; Comments click, the comments window
tests/test_core.py                         load_config reads jira_live_jql and jira_live_autofetch
dewey.example.toml, README.md, CHANGELOG.md, docs/plan.md
../asi_fusa_tools/ASI_FUSA_TOOLS.md                           version table, plans table, section "The JIRA Live Data window"
pyproject.toml, src/asi_dewey/version.py   0.5.0
```

No change to `schema/`, `storage/`, `repositories/`, `models/`, `io/`, `generate/`, `prefs.py`,
`gui/theme.py`, `gui/palettes.py`, `services/queries.py` (the cache tile and its query stay), or
`../asi_hopper`. Schema version stays 1; no new table, column or lookup.

## 6. Tests

**Verb and service (`tests/test_jira.py`)**, same replay fixture as today. The fixture index
**does** carry a recorded `searchJiraIssuesUsingJql` for `OPEN_JQL` (three issues, one page), so
the verb is tested end to end against the replay gateway, like `sync`; the house default JQL has
no fixture, which is itself a case. A stub Hopper is used only where the fixture cannot reach
(exactly-at-limit behaviour and null-heavy rows).

- `jira live --jql OPEN_JQL`: `ok`; `data["count"] == 3`; keys `["HWL-2572", "HWL-2575", "HWL-2620"]`
  in server order; `truncated is False`; `jql == OPEN_JQL`; `fetched_at` parses as an aware UTC
  datetime; every row has exactly the 16 keys of `LIVE_FIELDS`; `labels` and `components` are
  lists; HWL-2572's `parent_key == "HWL-1915"`, `status_category == "indeterminate"`,
  `issue_type == "Story"`; HWL-2620's `labels == ["VAT", "e-stop", "safety", "test-failure"]`.
- `--limit 2`: `count == 2`, `truncated is True`, keys are the first two, and `result.warnings[0]`
  contains `truncated at 2`. `--limit 3`: `count == 3`, `truncated is False`, no warning (the
  `limit + 1` probe asks for four, gets three). `--limit 0`: `not ok`, error names `limit`.
- No fixture for the house JQL: `jira live` with no `--jql` is `not ok` and its error starts with
  `Jira read failed:` (the `NotRecorded` path); the database is untouched.
- Config: with `ASI_DEWEY_CONFIG` pointing at a temp toml holding `jira_live_jql = "<OPEN_JQL>"`,
  `jira live` without `--jql` succeeds with 3 issues and `data["jql"] == OPEN_JQL`;
  `brain.jira.live_jql() == LIVE_JQL` when the key is absent; `brain.config["jira_live_autofetch"]`
  is `False` when the file says `jira_live_autofetch = false` and absent when the file says
  `jira_live_autofetch = "false"` (in `tests/test_core.py` next to the other `load_config` cases).
- Nothing written: after a successful `jira live`, `count jira_ticket` is 0, `audit_tail(10)` has
  no new entry, and `events.last(1)[0]` is `{"topic": "jira.live", "count": 3, "truncated": False,
  "jql": OPEN_JQL, "actor": "python", "fetched_at": ...}`.
- Service with a stub (no fixture needed): `monkeypatch.setattr(brain.jira, "open_hopper", lambda: stub)`
  where `stub.search(jql, *, all_pages, limit)` records its arguments and returns `limit` or
  fewer `IssueRecord`-shaped objects (a small frozen dataclass in the test with the attributes
  `live_row` reads, `parent` either `None` or an object with `.key`). Assert `search` was called
  with `all_pages=True, limit=limit + 1`; a stub returning exactly `limit + 1` records gives
  `truncated is True` and `count == limit`; a record with every optional attribute `None` and
  empty tuples maps to `null`s and `[]`s; `stub.close()` is called when the service opened the
  Hopper and not when one was passed in.
- `AuthRequired` from the stub's `search` becomes `not ok` with the login hint in `errors[0]`;
  `ImportError` from a monkeypatched `open_hopper` becomes `not ok` with `INSTALL_HINT`.
- `jira dance` still fails; `schema` for `jira` lists `live` among the action choices and `limit`
  with `type == "int"` and `default == 2000`.

**Window (`tests/test_gui.py`)**, real `MainWindow` on the `seeded` brain, `interactive=False`.
The screen is filled from a stubbed `run_quiet` (`monkeypatch.setattr(window, "run_quiet", fake)`
returning `Result.success(SAMPLE)`), where `SAMPLE` holds five hand-written rows covering two
statuses, all three categories, two types, two priorities, two assignees, one null assignee, one
null due date, labels, a parent, and keys `HWL-9`, `HWL-10`, `HWL-100`, `HWL-2`, `HWL-33`. No
replay gateway is needed in the GUI tests and no network is ever touched.

- Order: `[k for k, _ in window.factory.items()][:2] == ["dashboard", "jira_live"]`;
  `window.factory.title("jira_live") == "JIRA Live Data"`; the second `View` menu entry is
  `JIRA Live Data`; `window.nav.get(1).strip() == "JIRA LIVE DATA"`.
- Tile: on the dashboard, generating `<Button-1>` on the `jira_ticket` tile makes
  `window.current_key == "jira_live"` (with the stubbed `run_quiet`, so no fetch happens); the
  `fact` tile still opens `entity:fact`.
- First show fetches once: with the stub counting calls, `window.show("jira_live")` calls it
  once; `window.show("dashboard")` then `window.show("jira_live")` does not call it again;
  `window.jira_live.data is SAMPLE`; 5 rows in the tree; the toolbar label matches
  `r"^5 issues · fetched \d\d:\d\d · project = HWL"`; `count_var` is `5 of 5 issues`.
- Autofetch off: `monkeypatch.setitem(seeded.config, "jira_live_autofetch", False)`, show the
  screen, the stub is not called, the tree is empty, the label is `No fetch yet · press Refresh`;
  `screen.fetch()` then fills it.
- Refresh button: `screen.fetch()` calls the stub again and repaints; a stub that now returns
  `Result.failure("no Atlassian session for this account; run `asi-hopper auth login` once")`
  leaves the 5 rows in place, keeps `window.jira_live.ok`, and puts `Error: no Atlassian
  session` in `window.status_text()`. On a fresh window whose first fetch fails the same way:
  empty tree, label starts `Offline:`, `window.jira_live` is the failed Result, and a second
  `show` does not fetch again.
- Sorting: `screen.sort_by("key")` orders iids `HWL-2, HWL-9, HWL-10, HWL-33, HWL-100` (numeric,
  not lexical); a second `sort_by("key")` reverses it; `sort_by("due")` puts the null due last in
  both directions; the sorted heading text ends with `▲` then `▼`.
- Each filter: `filter_var.set("hwl-1")` leaves `HWL-10` and `HWL-100` (case-insensitive, key);
  `filter_var.set("brake")` matches on summary only; `filters["status"].set("Done")` then
  `_populate()` shows the done rows only and `count_var` reads `2 of 5 issues`;
  `filters["status_category"]` values are `["(all)", "new", "indeterminate", "done"]`;
  `filters["assignee"]` values end with `(none)` and selecting it shows the unassigned row;
  `filters["issue_type"]` and `filters["priority"]` each narrow to their rows; two filters
  combine with AND; `clear_filters()` restores 5 rows, every combobox to `(all)`, and the server
  order.
- Muted: every row with `status_category == "done"` has `"muted"` in `tree.item(iid, "tags")`
  together with its `odd`/`even` stripe tag, and no other row does;
  `tree.tag_configure("muted", "foreground") == window.theme.palette.muted`.
- Cells: `tree.set("HWL-9", "labels") == "safety, VAT"`, `tree.set("HWL-9", "created")` is 10
  characters, `tree.set("HWL-33", "assignee") == ""` for the null assignee.
- Open: `tree.focus("HWL-9"); screen.open_selected()` puts `Open: https://...HWL-9` in the status
  bar (not interactive, so no browser); with nothing focused the status bar says
  `Select an issue first`.
- Rebuild keeps the rows: `window.pick_theme("pink-noir")` with the screen current; afterwards
  `window.current_key == "jira_live"`, the stub was not called again, the tree has 5 rows, and
  `tree.tag_configure("muted", "foreground") == "#955073"` (pink-noir's `muted`).
- Event path: `seeded.events.publish("jira.live", count=0, jql="x", truncated=False,
  fetched_at="", actor="agent")` while the dashboard is current does not schedule a refresh
  (`window._refresh_job is None` right after); `entity.created` still does.
- Nothing written: after every case above `seeded.execute("count", entity="jira_ticket").data["count"] == 0`
  and the last audit entry is still the seed's.

**Comments: the verb (`tests/test_jira.py`)**. The recorded `getJiraIssue_HWL-2575.json` is
keyed with the `comment` field, so the `comments=True` path replays end to end; its history is
empty, so ordering and the row mapping are tested with a stub.

- `jira comments HWL-2575` on replay: `ok`; `data["key"] == "HWL-2575"`; `summary` starts with
  `STPA Step 4`; `url` ends with `/browse/HWL-2575`; `status` is a non-empty string; `count == 0`;
  `comments == []`; `fetched_at` parses as aware UTC. `jira comments hwl-2575` (lower case) gives
  the same answer. `jira comments HWL-1`: `not ok`, error starts with `Jira read failed:`.
  `jira comments` with no key: `not ok`, error names the key. Nothing written, no audit entry,
  and `events.last(1)` is the same before and after the call (no event).
- Stub: `open_hopper` returns a stub whose `get(key, *, comments)` asserts `comments is True`
  and returns a record with three `Comment`-shaped objects created `2026-10-01`, `2026-10-03`,
  `2026-10-02` (ids `c1`, `c3`, `c2`), one of them with `updated` later than `created` and one
  with `body=None`: the Result lists ids `["c3", "c2", "c1"]`, keeps `updated` as given, maps
  the `None` body to `""`, and has no `author_id` key. `AuthRequired` from the stub's `get`
  gives the login hint; `stub.close()` is called when the service opened the Hopper.
- `schema` for `jira` lists `comments` among the action choices.

**Comments: the window (`tests/test_gui.py`)**, with the `run_quiet` stub branching on
`action`: `live` returns `SAMPLE`, `comments` returns `COMMENTS` (three comments for `HWL-9`,
newest first as the verb would send them, one of them edited) and counts its calls per action.

- Click dispatch: the test windows are withdrawn and never mapped, so `bbox` and `identify_*`
  return empty and `event_generate` cannot land in a cell; the test monkeypatches
  `screen.tree.identify_column` to return `"#1"` and `identify_row` to return `"HWL-9"`, then
  calls `screen._on_click(SimpleNamespace(x=5, y=5))`: `"HWL-9"` is in `window.comment_windows`
  and the handler returned `"break"`. With `identify_column` returning `"#3"` nothing opens and
  the handler returns `None`. `tree.focus("HWL-9"); screen._on_key_c(None)` opens it too.
- The window: `win = window.open_comments("HWL-9")`; `win.title() == "HWL-9 — Comments"`;
  `win.cget("background") == window.theme.palette.bg`; the meta labels in `win.body.inner`, in
  order, start with the newest comment's author and `2026-10-26 15:02`, and the edited one ends
  with `· edited 2026-10-26 15:40`; the three `tk.Text` bodies are `disabled` and hold the
  bodies; `win.status_var.get()` matches `r"^3 comments · fetched \d\d:\d\d$"`.
- Second open: `window.open_comments("HWL-9") is win` and `len(window.comment_windows) == 1`;
  `open_comments("HWL-10")` makes two.
- Refresh: `win.fetch()` adds one `comments` call to the stub's count and the body still lists
  three. A stub now failing with `Result.failure("no Atlassian session ...")`: `win.fetch()`
  leaves the three blocks, `win.status_var.get().startswith("Error: no Atlassian session")`,
  `win.winfo_exists()`, and `window.status_text()` starts with `Error:`.
- Empty: a stub returning `count: 0, comments: []` for `HWL-2` shows one label `No comments.`.
- Close: `win.close()` removes the key from `comment_windows` and `win.winfo_exists()` is false.
  Theme pick with one open: after `window.pick_theme("pink-noir")`, `window.comment_windows == {}`
  and the old window's `<Destroy>` flag is set. Main-window close: open one, bind a `<Destroy>`
  flag on it, `window.close()`; the flag is set (this case uses its own window from `_open`,
  since it ends the window).
- Nothing written: `count jira_ticket` is still 0 after every case.

**Replay end to end once (`tests/test_jira.py`, GUI-free)**: `brain.execute("jira", action="live",
jql=OPEN_JQL, actor="gui")` and `brain.execute("jira", action="comments", key="HWL-2575",
actor="gui")` are what the windows send; asserting them here keeps the window tests free of the
fixture and the fixture tests free of Tk.

## 7. Rejected alternatives

- **Storing the live rows in a table.** Dewey already has the cache (`jira_ticket`, fed by
  `jira sync`) and it has a different job: a curated, ordered, workbook-exported view of the
  tickets the engineer follows. "All issues past and present" is thousands of rows that nobody
  wants in the workbook or in a `dump`; a second table would blur which one is the truth and
  invite edits to data Jira owns. Memory on the window object is enough for a view.
- **Server-side filtering per keystroke.** Every keystroke would be a JQL call: rate limit,
  latency, and a table that flickers. One fetch, then local filters, is instant and offline-safe.
- **A shared `asi_jira_screen` package.** The family rule: primary tools share conventions, not
  code. The twin plans and the family table are the agreement; a test in each repo guards the
  key, title and position.
- **Auto-refresh on a timer.** The owner asked for a refresh button only. A timer would also
  fetch while the engineer is typing a filter and would burn the rate limit while the window
  sits in the background.
- **`jira sync` with a wider JQL instead of a new verb.** Sync writes rows; the ask is to look,
  not to store. Mixing the two would make the cache grow with every look.
- **Reusing `EntityScreen` with a fake schema.** It carries a form, create/update/delete and
  `by_id` on integer ids; the live screen needs none of that and keys rows by issue key. A
  dedicated, read-only screen is smaller than the subclass would be.
- **Caching the fetch on the screen instance.** Lost on every theme pick (`set_theme` recreates
  screens), so a repaint would refetch. The window object outlives screens; see section 3.7.
- **`IssueRecord.to_row()` as the row.** It joins labels with `;`, calls the type `type` and the
  parent `parent`, and lacks reporter, resolution and components. The convention row keeps the
  `jira_ticket` vocabulary and lists as lists.
- **A real `ttk.Button` per row, overlaid on the Treeview.** Buttons placed with `place()` over
  cell bboxes must follow every scroll, sort, filter and resize, and `bbox` is empty for rows
  not on screen; the text cell with position-routed clicks costs nothing and never drifts.
- **An accent "link" tag on the Comments cell.** Treeview tags style the item, so the whole row
  would turn accent; the cell reads `[Comments]` and the cursor does the signalling.
- **Requesting the `comment` field in the live search to show a count.** Every page would carry
  every body of every issue, the fetch would be many times heavier, and the recorded search
  fixture would no longer match. A count is a per-issue call; the window shows the history.
- **A nav screen with a Back button for comments.** One ticket per view, several open at once,
  and the nav list is for the tool's own screens; a Toplevel per ticket does all three.
- **Publishing a `jira.comments` event.** Nothing anyone holds changes; see section 3.10.

## 8. Open items

- **2026-10-28 (0.7.3), done:** `jira_live_autofetch` now defaults to `false`, and `fetch()` runs
  the verb on a daemon worker thread (`WorkerFetch` in `gui/screens.py`, through the new
  `MainWindow.execute_quiet`) while the Tk thread polls with `after(100, ...)` and applies the
  Result. Why: the owner's window got stuck on a live fetch. The fetch (up to 2,000 issues at 50 a
  page, plus any gateway wait) ran on the Tk thread through `run_quiet`, so the window froze for
  its whole duration, and autofetch started it on the first show. The owner asked that neither
  tool connect automatically. The code in §3.7 shows the 0.5.0 shape; the status line,
  `window.jira_live`, the status-bar lines and the rebuild behaviour are unchanged, the toolbar
  label says "Fetching Jira … up to 2000 issues, this can take a minute" while the worker runs,
  Refresh is disabled meanwhile, and a theme pick or a close never waits on the worker. The
  comments window fetches the same way.
- Whether F5 on the live screen should fetch as well as repaint. Cheap either way; decide after
  using the button for a week.
- When the automation server lands (0.7.0), whether a `jira live` run by an agent should push its
  rows into an open window. Today the event carries counts only and the window ignores it; the
  verb's Result belongs to its caller. If wanted, the event would carry the rows or the window
  would re-run the verb on `jira.live` from another actor.
- Comment bodies are shown as the Markdown text Hopper gives (ADF is already rendered to
  Markdown by `adf_to_markdown`); bold, lists and links appear as their Markdown marks. A later
  plan may render Markdown into the `tk.Text` with tags; plain text first.
- Whether `[Comments]` should also appear on the dashboard's "Open Jira tickets" table. Not
  now: that table reads the cache; its rows do carry a `key`, so it is a small later step.
- Whether the toolbar should show the Jira site name next to the count, from `hopper.status()`.
  Not now: that is a second call and the status bar already shows the database.
- The family document's version table still says 0.2.0 for both primary tools and calls
  `asi_hopper` an empty folder; phase 5 updates the versions and the `asi_hopper` row should be
  corrected in the same edit if the 0.3.0 and 0.4.0 plans have not already done it.
- This plan assumes 0.4.0 (`prune-windows-plan.md`) has landed, but nothing in it depends on
  that: registration after `dashboard` is positional, and `TILE_TARGETS` works with or without
  the prune's tile guard (before the prune the `jira_ticket` tile simply opens the live screen
  instead of the cache screen).

*Written 2026-10-27.*
