# ASI Dewey — Plan

**Status:** Draft 0.1 (first pass, more prompts to come)
**Started:** 2026-10-27
**Owner:** FuSa engineer

---

## 1. Vision

ASI Dewey is a Python desktop application and FuSa (functional safety) API in one package.

- A **custom tkinter GUI** gives a human engineer a set of screens to enter and maintain
  functional-safety working knowledge: tasks, facts, functions, use cases, links, Jira
  tickets, QMS references, people, and the safety plan deliverables matrix.
- A **database** is the single source of truth. Every screen reads from it and writes to it.
- The Excel workbook **`dewey.xlsx` is a generated view of the model**, not the model
  itself. At any moment the user (or an automation) can regenerate it from the database.
- Every table can be **dumped to JSON** (and loaded back) for portability, diffing, versioning,
  and feeding AI tools.
- A **robust automation command layer** lets a human engineer, an AI agent, or both at the same
  time "puppet" the tool. Everything the GUI can do, a command can do.
- The **factory design pattern** is used as much as possible: models, repositories, screens,
  exporters, importers, and commands are all created through registries and factories so new
  table types and new screens are added by registration, not by editing core code.

The end state is a FuSa API with a GUI on top of it, not a GUI with a database bolted on.

---

## 2. Domain model (seeded from the current workbook)

The existing workbook has 11 sheets. Each meaningful sheet becomes a table (entity). Column
names below are the current headers, normalized to snake_case.

| Entity | Source sheet | Fields (current) | Notes |
|---|---|---|---|
| `Task` | tasks | order, task_class, name, start, end, comments | Add `status` later |
| `Fact` | facts | order, name, text | |
| `MachineFunction` | WL functions | name, description | Duplicate "tool curl" exists today |
| `UseCase` | WL use cases | name, description | |
| `Link` | links | order, link_class, name, url | |
| `JiraTicket` | JIRA | order, name, status, url, + key, issue_type, priority, assignee, parent_key, labels, updated, synced_at | Rows with a key are refreshed by `jira sync` through asi_hopper (read only) |
| `QmsDocument` | QMS | order, name, url | |
| `Person` | people | order, person_class, nickname, text | Split into name + email later |
| `SafetyPlanRow` | Safety Plan | order, pdp_phase, lifecycle_phase, deliverable, release_location, qms_reference, author, verifier, reviewer flags (7 roles), deadline, status | Columns I–M (all zeros) and N (empty) look abandoned; drop them |
| `ReviewerType` | Sheet4 | name | Lookup list for the Safety Plan reviewer columns |

Sheet3 is empty and is not modelled.

Design rules for the model:

- Every entity gets a surrogate primary key `id` plus `created_at` / `updated_at`.
- `order` columns remain as user-controlled display ordering, not as keys.
- Lookup lists (task_class, link_class, person_class, reviewer types, PDP phases,
  lifecycle phases, status values) become small reference tables so screens can offer
  dropdowns and the Excel export can add data validation.
- Entities are declared once, in a schema definition, and everything else (DB table, GUI
  form, Excel sheet, JSON shape, command arguments) is derived from that definition by
  factories. Adding a new entity means adding one schema definition and registering it.

---

## 3. Architecture

Layered, with every layer talking to the one below it through an interface, and every concrete
implementation produced by a factory.

```
+----------------------------------------------------------------+
|  Front ends                                                    |
|   tkinter GUI        CLI           Automation server (AI/human) |
+----------------------------------------------------------------+
|  Command layer  (single entry point: Command objects)          |
|   CommandFactory -> Command.execute(context) -> Result          |
+----------------------------------------------------------------+
|  Service layer  (use cases: create/update/delete/list/export)  |
+----------------------------------------------------------------+
|  Repository layer  (RepositoryFactory -> per-entity repository)|
+----------------------------------------------------------------+
|  Storage: SQLite (default)   |  Exporters/Importers            |
|                              |   ExcelExporter, JsonExporter,   |
|                              |   JsonImporter, (ExcelImporter)  |
+----------------------------------------------------------------+
```

Key points:

- **One command path.** The GUI, the CLI, and the automation server all build Command objects
  and hand them to the same dispatcher. There is no GUI-only logic. This is what makes the
  tool puppetable.
- **Schema-driven factories.** A `SchemaRegistry` holds one `EntitySchema` per table. From it:
  `ModelFactory` builds dataclasses, `RepositoryFactory` builds SQLite repositories,
  `ScreenFactory` builds tkinter screens, `SheetFactory` builds Excel sheets,
  `CommandFactory` builds the CRUD command set.
- **Plugins by registration.** A new entity, exporter, or screen is registered with a
  decorator (`@register_entity`, `@register_exporter`, `@register_screen`) and picked up by
  the factories at start-up.

### 3.1 Factory inventory

| Factory | Produces | Keyed by |
|---|---|---|
| `ModelFactory` | dataclass for an entity | entity name |
| `RepositoryFactory` | repository bound to a storage backend | entity name, backend name |
| `StorageFactory` | storage backend (SQLite now, others later) | backend name |
| `ScreenFactory` | tkinter frame for an entity or a special screen | screen name |
| `WidgetFactory` | field widget from a field type (text, multiline, date, url, enum, bool, int) | field type |
| `ExporterFactory` | exporter (`excel`, `json`) | format name |
| `ImporterFactory` | importer (`json`, later `excel`) | format name |
| `CommandFactory` | command object from a verb and arguments | command verb |
| `FrontEndFactory` | GUI, CLI, or server front end | mode |

---

## 4. Database

- **SQLite** file next to the application (`dewey.db`), one table per entity plus the
  lookup tables. No server, no setup, easy to back up and to put under OneDrive.
- Schema is generated from the `EntitySchema` definitions; a small migration table records
  the schema version so later field additions are applied automatically.
- Repositories expose: `get(id)`, `list(filter, order_by)`, `create(data)`, `update(id, data)`,
  `delete(id)`, `bulk_upsert(rows)`.
- Every write is wrapped in a transaction and logged to an `audit_log` table (who/what/when,
  including whether the actor was the GUI, the CLI, or an automation client). This matters
  when a human and an AI are both driving.

---

## 5. Excel generation (the workbook as a view)

- `ExcelExporter` walks the `SchemaRegistry`, and for each entity asks `SheetFactory` for a
  sheet builder. Output is `dewey.xlsx` with the same sheet names and column headers the
  workbook has today, so the file stays familiar.
- Headers bold, frozen top row, autofilter on, sensible column widths, dates formatted,
  URLs written as hyperlinks, enum columns given data validation from the lookup tables.
- Export is **full regeneration**, never in-place patching. If the target file is locked
  (open in Excel), export writes to a timestamped sibling and reports that.
- Optional later: `ExcelImporter` to pull edits back from the workbook, with a diff preview,
  for people who prefer editing in Excel.

---

## 6. JSON dump and load

- `dump` writes one JSON file per entity, or one combined file, with a top-level envelope:
  `{"schema_version": ..., "exported_at": ..., "entity": ..., "rows": [...]}`.
- `load` reads the same shape back. Modes: `replace` (wipe and insert), `merge` (upsert by id),
  `append` (new ids).
- JSON is the interchange format for AI agents: an agent can read the dump, reason about it,
  and send back commands or a modified dump.

---

## 7. Automation and puppeting

Goal: a human, an AI, or both can drive the application, at any time, with the same set of
commands the GUI uses internally.

### 7.1 Command vocabulary (first cut)

```
list    <entity> [--filter k=v] [--order-by field]
get     <entity> <id>
create  <entity> --data '{...}'
update  <entity> <id> --data '{...}'
delete  <entity> <id>
dump    [--entity <entity>] [--out <path>]
load    <path> [--mode replace|merge|append]
export  excel [--out <path>]
schema  [<entity>]                 # describe entities and fields
theme   [<key>]                    # latch a window theme; recolours a running window (0.3.0, remote in 0.7.0)
session [--quit]                   # the automation session of a running window; opens no Brain (0.7.0)
status                             # health, db path, row counts, locks
```

Every command returns a structured `Result` (`ok`, `data`, `errors`, `warnings`) that
serializes to JSON.

GUI puppeting is not a verb (0.7.0, decided in `automation-server-plan.md`): without a window
there is nothing to show, so it lives on the server as endpoints, `GET /screens` (the navigation
list with the current one marked) and `POST /screen {"show": key}` (show a screen exactly as a
click does). The `fill` / `submit` / `cancel` puppeting of a screen's form sketched here earlier
is still open: it needs a per-screen contract for widgets and comes after approval mode, if
still wanted.

### 7.2 Transports

- **In-process API**: `brain.execute(Command)` for Python callers and tests.
- **CLI**: `asi-dewey <verb> ...` for humans and for AI agents that have a shell.
- **Local automation server** (0.7.0, `automation/server.py`): HTTP/1.1 and JSON `Result`
  answers on `127.0.0.1` and an ephemeral port, served by the standard library on a daemon
  thread the window owns; a per-launch bearer token in the session file
  `%LOCALAPPDATA%\asi\dewey\session.json` (`automation/session.py`, `$ASI_DEWEY_SESSION`).
  `POST /execute` accepts the same command JSON as the dispatcher's wire format and runs it on
  the Tk thread (the main-thread handshake: a queue drained every 50 ms, the handler waiting on
  an `Event`), so a command from the server updates the screen the human is looking at.
  `GET /status`, `GET /screens`, `POST /screen`, `GET /events?since=<n>` (every event carries
  `seq`), `POST /quit`. Since the family lock (0.6.0) the CLI is refused while a window is open,
  so this is the only way to drive a running window: the CLI **forwards** a command refused in
  favour of a Dewey window with a live session and prints the forwarded `Result` untouched
  (exit 0 or 1); a Kletz window, a dead session or `--no-forward` is still exit 3.
  `ASI_DEWEY_AUTOMATION=off` or `--no-server` turns it off. See
  [automation-server-plan.md](automation-server-plan.md).
- **Script files**: a `.jsonl` of commands can be replayed (`asi-dewey run script.jsonl`),
  which doubles as a macro recorder output for the GUI.

### 7.3 Human and AI together

- An **event bus** publishes every state change. The GUI refreshes on events, so a human sees
  AI edits appear live, and vice versa.
- The audit log records the actor for each change, so "who did this" is always answerable.
- An optional **approval mode** lets the human require confirmation in the GUI before
  commands from the automation server commit. Off by default; on when mood demands it. Still
  planned (the next plan after 0.7.0); it will sit behind `MainWindow.remote_guard`, the hook
  the server passes every remote command through, which today knows one safety rule: a remote
  `theme` pick is refused, never prompted for, while the open screen has unsaved edits.
- **Remote and forwarded commands carry their actor** (0.7.0): `/execute` runs with the actor the
  agent sent (`agent` by default), a forwarded CLI command with `--actor` (`cli` by default), so
  the audit log and the events say who did it; the window's own edits stay `gui`. The server
  never opens a dialog: every job runs on the Tk thread with a request waiting on it.
- **One primary tool at a time** (decided 2026-10-27, shipped in 0.6.0): only one process of Dewey or
  Kletz holds an open `Brain` at any moment, enforced by the family lock described in
  [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md). "Together" therefore means inside the one running
  process: the window plus the automation server, never the window plus a second CLI process.
  See [single-instance-plan.md](single-instance-plan.md).

---

## 8. tkinter GUI

- One main window with a left navigation list (one entry per registered screen) and a content
  area. `ScreenFactory` produces the content frames.
- Generic **entity screen** (produced for every entity from its schema): a table view at the
  top, a form below, buttons for New / Save / Delete / Duplicate, search box, column sort.
- Special screens: Dashboard (counts, open Jira, this week's tasks), Export / Import, Generate;
  `HIDDEN_ENTITY_SCREENS` in `gui/screens.py` names the entities that have no screen
  (`jira_ticket`, `safety_plan_row`, 0.4.0). Still planned: Automation (server on/off, live
  command log, approval toggle; the status-bar port, `asi-dewey session` and `/events` cover
  the need since 0.7.0), Settings (db path, workbook path).
- **The status bar** (0.7.0): the online indicator reads `◉ ONLINE :51234` while the window's
  automation server is up and `◉ ONLINE` otherwise (`online_var`); next to it the **theme
  badge** (`badge_var`), the theme title upper-cased with any parenthetical dropped
  (`CYAN NEON`, `PINK DAY`, `PLAIN`), in the mono font, style `StatusMuted.TLabel`; then the
  status text and, on the right, the database path. Both labels are rebuilt from `self.server`
  and `self.theme` by `set_theme`; the server is owned by the window, not by any widget, so it
  survives the rebuild. The About box names the session address and file.
- **JIRA Live Data** (0.5.0): screen `jira_live`, second after the dashboard, a convention shared
  by name with asi_kletz (key, title, verbs, columns, filters; `ASI_FUSA_TOOLS.md`, "The JIRA Live
  Data window"). One Refresh button runs `jira live` through `MainWindow.run_quiet`; the Result
  lives on the window object for the session, so a theme rebuild repaints without a refetch.
  Fifteen columns with `[Comments]` first (a click routed by `identify_column` opens one
  `JiraCommentsWindow` Toplevel per ticket, fed by `jira comments`, newest first), local
  filters, sort on every other column, done rows muted. Nothing is written to the database;
  the `jira_ticket` cache and the dashboard tile stay, and the tile opens this screen.
  See [jira-live-data-plan.md](jira-live-data-plan.md).
- Field widgets come from `WidgetFactory` so a `url` field always gets an "Open" button, a
  `date` field always gets a date picker, an enum always gets a dropdown, and so on.
- ttk themed widgets, keyboard-first (Ctrl+N new, Ctrl+S save, Ctrl+E export).
- **Themes** (0.3.0): a `ThemeFactory` keyed like everything else. The family palette
  (`gui/palettes.py`, 8 hue families x 4 tones = 32 palettes, identical by convention in every
  ASI primary tool and checked by a digest test against `ASI_FUSA_TOOLS.md`) plus `plain`. The
  house default is `cyan-neon` (the former `tron`, kept as an alias). A read-only `THEME`
  combobox at the foot of the navigation column and `View > Theme` repaint the window at once
  by rebuilding its children (`Theme.apply` is re-entrant) and latch the choice in a per-person
  `prefs.json` (`prefs.py`, `$ASI_DEWEY_PREFS`); the `theme` verb does the same and publishes
  `theme.changed`. Precedence: `--theme`, `$ASI_DEWEY_THEME`, the latch, the house default.
  See [theme-palette-plan.md](theme-palette-plan.md).

---

## 9. Project layout (proposed)

*As proposed in Draft 0.1. The real tree (a `src/` layout, Python 3.13, `tests/` beside the
package, `locks.py`, `prefs.py`, `generate/`) is the "Layout" section of `README.md`.*

```
asi_dewey/
  __init__.py
  app.py                # entry point, FrontEndFactory
  schema/               # EntitySchema definitions, registry, lookups
  models/               # ModelFactory
  storage/              # StorageFactory, SQLite backend, migrations, audit log
  repositories/         # RepositoryFactory
  services/             # use-case services
  commands/             # Command base, CommandFactory, dispatcher, Result
  io/                   # ExporterFactory, ImporterFactory, excel, json
  gui/                  # tkinter: main window, ScreenFactory, WidgetFactory, screens
  automation/           # CLI, local server, script runner, event bus
  tests/
pyproject.toml
README.md
```

Dependencies: Python 3.11+, `openpyxl`, standard library `tkinter`, `sqlite3`, `json`,
`argparse`. Nothing else unless a later prompt calls for it.

---

## 10. Delivery phases

1. **Core**: schema registry, models, SQLite storage, repositories, commands, CLI, JSON dump
   and load. Seed the database from the current workbook.
2. **Excel export**: regenerate `dewey.xlsx` from the database, byte-for-byte usable.
3. **GUI**: main window, generic entity screens, export screen.
4. **Automation**: local server, event bus, GUI puppeting commands, script replay, audit log.
5. **Polish**: dashboard, Safety Plan matrix screen (removed again in phase 8), approval mode,
   Excel import.
6. **Diagrams and documents** (0.2.0): `diagram` and `document` verbs, catalogs behind
   `DiagramFactory` / `DocumentFactory`, and the Generate screen, built on asi_escher and
   asi_gutenberg. See [escher-gutenberg-integration-plan.md](escher-gutenberg-integration-plan.md).
7. **One primary tool at a time** (planned for 0.3.0, shipped in 0.6.0 after the window work of
   0.3.0 to 0.5.0): the family lock in `locks.py`, `PrimaryToolBusy`, `--wait`, exit code 3, the
   Retry / Quit dialog, `lock_dir` and `locks` in `status`.
   See [single-instance-plan.md](single-instance-plan.md). The automation server (0.7.0,
   [automation-server-plan.md](automation-server-plan.md)) follows it.
8. **Prune windows** (0.4.0): the JIRA, Safety Plan and Safety Plan Matrix screens leave the
   window through `HIDDEN_ENTITY_SCREENS`; the entities, sheets, verbs and the dashboard tile
   stay. The Safety Plan is edited in asi_kletz; the live Jira view is 0.5.0.
   See [prune-windows-plan.md](prune-windows-plan.md).
9. **JIRA Live Data** (0.5.0): `jira live` and `jira comments` on the `jira` verb, the
   `jira_live` screen right below the dashboard, the per-row `[Comments]` button and the
   comments window; the same convention implemented in asi_kletz.
   See [jira-live-data-plan.md](jira-live-data-plan.md).
10. **The local automation server** (0.7.0): `automation/server.py` and `automation/session.py`,
    the main-thread handshake, the six endpoints, `seq` on every event, the CLI forwarding
    branch and `--no-forward`, the `session` verb, the theme badge, `remote_guard`, the
    puppeting endpoints `/screens` and `/screen`; the same convention implemented in asi_kletz.
    See [automation-server-plan.md](automation-server-plan.md). Next: approval mode.

---

## 11. Open questions (to be answered in later prompts)

- Which additional entities or screens beyond the current 10 sheets?
- Single user on one machine, or shared database on OneDrive with several people?
- Does the AI puppet through the CLI, the local server, or both? (Both, since 0.7.0: the CLI
  forwards to the server of a running window.)
- Should the Safety Plan reviewer flags stay as one-hot columns in Excel, or become a
  single "reviewer" enum per row?
- Naming: package name `asi_dewey`, command name `asi-dewey`? (Yes, since 0.1.0.)

---

## 12. Change log

- 2026-10-27 Draft 0.1: vision, domain model from the workbook, layered architecture with
  factory inventory, database, Excel view, JSON dump/load, automation and puppeting, GUI,
  layout, phases, open questions.
- 2026-10-27 0.3.0: section 8 gains the family palette and the latching theme picker
  (`theme-palette-plan.md`): 32 shared palettes, `cyan-neon` house default with `tron` as an
  alias, `prefs.py`, the `theme` verb, live repaint by rebuilding.
- 2026-10-27 0.4.0: section 8 drops the Safety Plan matrix screen and gains
  `HIDDEN_ENTITY_SCREENS` (`prune-windows-plan.md`): the JIRA, Safety Plan and Safety Plan
  Matrix screens leave the window, the entities stay; section 10 gains phase 8.
- 2026-10-27 0.5.0: section 8 gains the JIRA Live Data screen and the comments window
  (`jira-live-data-plan.md`): `jira live` / `jira comments`, the fetch held on the window
  object, the `[Comments]` column, the family convention; section 10 gains phase 9.
- 2026-10-27 0.6.0: section 7.3 and phase 7 record the family lock as shipped
  (`single-instance-plan.md`, re-targeted from 0.3.0): `locks.py`, `PrimaryToolBusy`, `--wait`,
  exit code 3, the busy dialog; the automation server is next (0.7.0).
- 2026-10-27 0.7.0: sections 7.1 to 7.3 record the local automation server as shipped
  (`automation-server-plan.md`): the session file, the six endpoints, the main-thread
  handshake, CLI forwarding with `--no-forward`, the `session` verb, puppeting as endpoints
  rather than a verb, the actor of remote commands; section 8 gains the status bar (port in the
  online indicator, theme badge) and `remote_guard`; section 10 gains phase 10. Approval mode
  is the next plan.
