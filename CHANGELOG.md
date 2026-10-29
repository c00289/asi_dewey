# Changelog

All notable changes to ASI Dewey are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0 releases may break anything.

## [Unreleased]

### Planned
- Approval mode: human confirms agent commands before they commit (behind `remote_guard`).
- Excel import diff preview; `fill` / `submit` / `cancel` puppeting of a screen's form; a
  `View > Automation` submenu or screen; date picker widget.

## [0.10.0] - 2026-10-29

The STPA step objects, Phase D of
[asi_hopper/docs/confluence-integration-plan.md](../asi_hopper/docs/confluence-integration-plan.md)
(section 7). The owner, 2026-10-29: "there may be a way to tie in individual stpa objects to confluence".
The STPA pages carry losses, hazards, unsafe control actions, loss scenarios and constraints with stable
local codes; Dewey now holds them as entities, each one citing the page, the version and the section it
came from, read through asi_hopper 0.1.9's page anatomy (Phase C) from a Hopper evidence bundle, and
links the UCAs to the control structures of 0.9.0. Confluence stays read only and the truth for the text;
Dewey owns the links and the notes. Schema version 3 to 4. The plan foresaw this as 0.9.0; that number
went to the control structures the same day, and the control-structure screen (phase 3 of
docs/control-structure-plan.md) shares 0.10.0 with it.

Control structures, phase 3 of docs/control-structure-plan.md: the screen. The owner, 2026-10-29:
"a screen that is used as a CRUD for STPA control structures… the user can export them to their
folder of preference… there must be Select all / Select none buttons, the default must be drawio
png". The screen changes no table: schema version 4 is the step objects' above.

### Added
- **Six entities** (`schema/definitions.py`): `stpa_analysis` (name, slug, system, status Draft / Reviewed /
  Baselined, `control_structure`, `source_kind` confluence / hand, `source_page_id`, `source_url`,
  `source_version`, `source_body_sha256`, `source_taken_at`, `source_bundle`, note) and its parts
  `stpa_loss` (code, text), `stpa_hazard` (code, text, parent, losses, retired), `stpa_uca` (code,
  controller, control_action, category, text, hazards, retired, duplicate_of, cs_controller, cs_signal),
  `stpa_scenario` (row, uca, counterpart, types, causal_factors, beliefs, constraints, retired) and
  `stpa_constraint` (code, text), every part with `cite` (`page <id> v<version> § <heading> (<anchor
  url>)`) and `note`, every row with its hidden `uid`; lists as JSON arrays in text columns. Lookups
  `stpa_status`, `stpa_source_kind`, `stpa_uca_category`. One sheet each (`STPA analyses` ... `STPA
  constraints`); the JSON dump carries them.
- **The service rules** (`services/stpa_service.py`, one `EntityService` subclass per entity, registered
  beside the control-structure rules): a part names an analysis that exists; a code is unique within the
  analysis and immutable while rows point at it; a hazard listed on a UCA, a loss on a hazard, a
  constraint or the UCA of a scenario must exist, as a warning, never a refusal (the pages cite `[H4]`
  where only H4.3 to H4.5 are listed); a dotted hazard's parent is the code before its last dot when that
  hazard exists; a scenario type is 1 to 4; one analysis per (page id, version); the `source_*` of an
  analysis read from Confluence move only through `refresh`; an analysis with parts is deleted with
  `cascade` or refused. `StpaService` (`brain.stpa`): `resolve`, `parts`, `dataset`,
  `create_from_dataset` (one transaction, audited once as `stpa.new`, forward references known to the
  load), `duplicate`, `delete`, `validate` (dangling codes, UCAs without a scenario, constraints only
  referenced, duplicate texts, a scenario without a UCA, UCAs naming a controller the linked structure
  lacks), `compare` (the refresh report by code: new, changed, retired, removed), `apply_refresh` (page
  fields written, every cite moved to the new version, the analysis's `source_*` moved, every
  Dewey-side field kept, one audit entry per object plus `stpa.refresh`), `link_structure` (controller
  text to `cs_controller.name` or `key`, control action to the names of the signals leaving it; exact
  matches apply, partial ones are reported). Events `stpa.changed`, `stpa.exported`.
- **The reader** (`stpa/confluence_reader.py`): pure functions over asi_hopper's `sections`, `tables`,
  `strike`, `split_on_bold` and `links`; the Markdown body plus the citation context in, the dataset out,
  never raw Atlassian JSON. Hazards and losses by line (a struck line retired, a dotted code's parent);
  UCAs from the first context table (the controller carried down, the four categories by column, each
  cell cut at its bold runs, hazards from the escaped `[H1, H2.1]`, a code inside `~~` retired,
  `(duplicate of **UCA7**)` read as the previous UCA's twin, an unbolded `UCA8 text` cell read by its
  code, a cell that links to another page a warning naming it, a hazard the page does not list a
  warning); scenarios and constraints from the first loss-scenario table (the UCA or its counterpart
  `CAn` at the start of the cell, `Type (n)`, the `Belief:` runs, every `CSTRn` of the constraints cell
  with its text, `and`-joined references, the first row that spells a constraint out winning, an empty
  UCA cell kept with a warning).
- **The factory** (`stpa/stpa_factory.py`, `brain.stpa_factory`): `StpaFactory` with the control-structure
  factory's `Builder` shape and its own registry: `blank`, `from_bundle` (the primary builder: a Hopper
  Confluence bundle's `manifest.json`, `pages.json` and `pages/<id>.md`, the page picked with `--page`
  when the bundle holds several, the `source_*` from the manifest, the comments kept for the report),
  `from_confluence` (`hopper.evidence.snapshot_pages` of the page with its comments into `evidence_dir`,
  then `from_bundle`; a missing session or a failed read is one line, never a browser), `clone`;
  `register_stpa_builder` adds one. `reread` for the refresh (a bundle `--from`, else a new snapshot).
  `export` writes `<out>/<slug>.xlsx` (the six sheets of one analysis), `<slug>_report.md|docx|pdf`
  (the `stpa_report` document) and `<slug>_trace.svg|png` (the `stpa_trace` diagram); default `xlsx`,
  `md`, `png`; audited as `stpa.export`, published as `stpa.exported`.
- **The `stpa` verb** (`commands/stpa.py`): `list | get <id> | builders | new <builder> [--name --slug
  --system --from --page --out] | refresh <id> [--from <bundle>] [--apply] | validate <id> | link <id>
  --structure <slug> [--apply] | export <id> [--out <dir>] [--format xlsx|md|docx|pdf|svg|png]... [--all]
  | delete <id> [--cascade]`; an analysis by id, uid or slug; every answer a JSON `Result`, the reader's
  warnings first.
- **Views**: the `stpa_report` document (the source, losses, hazards, the UCAs by controller and
  category, the scenarios, the constraints with the rows that name them, the trace figure, every object
  with its citation, the bundle's review comments as an appendix without authors) and the `stpa_trace`
  diagram (hazards, UCAs, scenarios, constraints as four columns left to right with the edges the page
  states, a retired UCA in the state tint, a duplicate a dashed edge; once linked to a structure, a
  swimlane per controller with lanes for the hazards and the constraints), both with `--param
  analysis=<slug>`.
- **The screen** (`gui/stpa_screen.py`, *STPA analyses*): the analyses with their counts, the parts of
  the selected one as tabs (read-only tables, no `id`, `order` or `uid` column), New from… with the
  builders, Validate, Link structure…, Export…, Delete, and Refresh from Confluence: the report runs
  on a worker thread polled with `after`, is shown in the Report tab, and `--apply` runs on the Tk
  thread once confirmed. The six entities are in `HIDDEN_ENTITY_SCREENS`; the Dashboard tiles the
  analyses and not the five parts.
- **Configuration**: `evidence_dir` in `dewey.toml` (a path, relative to the file; default `evidence/`
  beside the database; `$ASI_DEWEY_EVIDENCE` overrides it); `status` reports it as `evidence_dir`.
- `tests/fixtures/dewey-0.9.0.db`: a small 0.9.0 database for the migration test;
  `tests/fixtures/conveyor-gate-stpa.md`: the synthetic STPA page.
- **The Control structures screen** (`gui/control_structure_screen.py`, navigation entry "Control
  structures", `/screen {"show": "control_structures"}`, the Dashboard's CS STRUCTURES tile opens
  it). Left, the structures (name, system, status, revision, the six counts) with New from… (a dialog
  listing the factory's builders, their availability and the options each takes: name, system, a
  file or folder picker for `from_drawio` / `from_datasets`, a source structure for `clone`),
  Duplicate, Delete (asks, then `cascade`), Import draw.io… (the file keeps its name under the next
  free slug, so the round trip imports beside its origin), Validate (errors, warnings and info in the
  status bar and a panel under the list) and Export…. Middle, the selected structure's parts as a
  stacked tree (`stack()`: a controller row, under it its algorithms, its process-model entries and
  the arrows that leave it with their signals; the notes at the end; unique iids, a repeated group
  suffixed `#2`), a search box keeping the lines that open a match's groups, and a form for the
  selected row (controller / algorithm / process-model entry / edge / signal / note; the keys of
  controllers and edges offered in a list; lists one item per line) with Save, New child (the kind
  depending on the selection) and Delete. Right, the preview: escher's PNG of the structure rendered
  off the Tk thread when a structure is selected and after every save into `figures/` under the out
  folder (with its `.drawio`), scaled to fit (Pillow, which asi_escher brings), the OCR verdict and
  the layout-issue count under it, Re-render, and Open in VS Code on the `.drawio` when `code` is on
  the PATH. Every button calls a verb through the window.
- **The Export… dialog**: the destination folder (remembered in the preferences as `cs_export_dir`,
  the last one used), the three format check boxes with **Select all** and **Select none**, `drawio`
  and `png` checked by default, an OCR check box (on by default), a preview of the file names,
  Export. The work is the `cs export` verb on a worker thread ("Exporting…" meanwhile); the result
  names every file in the status bar and the dialog with the OCR verdict, and Open in VS Code on the
  written `.drawio`.
- `gui/background.py`: `BackgroundFetch`, the family's pattern (asi_kletz's Jira fetches) for work
  that takes seconds: one `window.execute_quiet(verb, ...)` or any callable on a daemon thread, polled
  from the Tk thread with `after`, nobody joins it. `MainWindow.execute_quiet` (`Brain.execute` as
  `gui` and nothing else) and `MainWindow.report` (what `run` says about a Result, for a fetch that
  ran off the thread).
- `ControlStructureFactory.build_files(diagram, out, name, formats, ocr=)`: the escher call alone, no
  database, no audit, no event; `export` wraps it with the audit and the event, the preview calls it
  with a diagram made on the Tk thread. `preview_dir()` is `figures/` under the out folder.
- `cs validate` reports `info` beside `errors` and `warnings`.

### Changed
- **Schema version 4.** A 0.9.x database opens with the six tables created, nothing altered, no row
  touched; the 0.9.0 fixture test counts them.
- `uv.lock` takes asi_dewey 0.10.0; asi_hopper stays 0.1.9 (`sections`, `find_section`, `tables`,
  `strike`, `split_on_bold`, `links`, `PageSource`, `snapshot_pages`, the error classes: what the reader
  and the factory import; nothing from `asi_hopper.gateway`).
- **Shared feedback is not a warning.** A signal carried by two edges that leave the same controller
  (one feedback to two receivers; the owner's structure has FB-05 and FB-11 that way) is legitimate:
  no warning when a file is loaded whole, no refusal when typed, `cs validate` lists it under `info`
  ("signal FB-11 is shared by 2 edges from perception: e7, e10", the edges in their order). A
  duplicate id on edges from different controllers stays a warning loaded and a refusal typed.
- The Dashboard tile of an entity with a screen of its own (`TILE_SCREENS`) opens that screen; the
  seven control-structure entities stay in `HIDDEN_ENTITY_SCREENS` (one screen, not seven tables).
- The window refreshes no screen on `cs.exported` (no row changed), as on `jira.live`.
- Version 0.10.0 in `pyproject.toml`, `version.py`, the README and `uv.lock`, which takes asi_escher 0.2.1
  (peers on one tier, a wider canvas, UTF-8 in the OCR gate), what its checkout declares.

### Tests
- 222 to 240. `test_stpa.py`: the reader on the synthetic page (2 losses, 5 hazards with a parent and a
  retired one, 8 UCAs with their categories and hazards, UCA3 retired and the duplicate of UCA6, the link
  cell and the unknown hazard H9 as warnings, 10 scenario rows with types, beliefs, counterparts and
  constraints, 6 constraints with the spelled-out text kept, the cite format); `from_bundle`, `blank`,
  `clone` and the catalog; `from_confluence` on asi_hopper's replay fixtures (5 hazards, 8 UCAs, 12 rows,
  7 constraints; a refresh of the unchanged page reports nothing); every rule and refusal; cascade delete;
  `validate`; every `stpa` verb and the command line in the acceptance form; `refresh` against the same
  bundle (nothing) and a changed one (new hazard, changed text, retired UCA, a constraint no longer
  spelled out), applied with the note, the links and the status kept and every cite moved; `link
  --structure` against a small synthetic structure (five exact, three partial, the exact ones written,
  validate naming the controller the structure lacks); the report and the trace rendering, with and
  without swimlanes; the export's six sheets, triplet and pictures with the audit and the event;
  dump/load and the workbook round trip; the 0.9.0 migration; the screen (create, validate, export,
  refresh off the Tk thread, apply, delete). The existing tests count 22 entities and 22 sheets; the
  window tests check the entity screens and the two feature screens by name, not by a count.
- 222 to 234. `test_control_structure_screen.py`, the window fixture: the screen registered, the
  tile and `/screen`; `stack()` on the synthetic structure (34 lines, unique iids, a repeated key
  suffixed, an orphan edge painted); the tree, the form filled by a selection, the search; Save and
  New child through `update` / `create` as `gui`, a refusal as a status-bar error, the preview
  re-rendered after a save; Delete asking first then cascading (an edge with its signals, a controller
  with its algorithms, the structure with everything); New from… blank and clone, the template
  listed unavailable, a blank name refused; Duplicate and Import draw.io… (the real escher writes the
  file); Validate showing the warning, the info and an error; the Export… dialog's defaults (drawio
  and png, OCR on), Select all / Select none, the file-name preview, Export calling `cs export` with
  the chosen formats (escher's `build` monkeypatched to write stub files, the OCR report competent),
  the status bar and the audit as `gui`, the folder remembered in the preferences, `--no-ocr` when the
  box is off, a failed export reported; Open in VS Code. `test_control_structures.py`: a shared
  signal from one controller loaded, typed and validated as info, a stranger still refused. The
  navigation counts eleven screens.

## [0.9.0] - 2026-10-29

Control structures, phase 2 of docs/control-structure-plan.md. The owner, 2026-10-29: "introduce a
screen that is used as a CRUD for STPA control structures; the idea is that we would be able to use
the factory design pattern to build a control structure, or many; we need to make control structures
like the one in Roy's Brain, feel free to use the schema; users make control architectures that we
will use for STPA later, and the user can export them to their folder of preference, selecting the
format ... the default must be drawio png"; and, of every diagram, "use OCR on the PNG so that the
final diagrams are competent" and "all image stuff is handled through escher". Phase 1 shipped as
asi_escher 0.2.0 (the `control_structure` kind, `to_drawio`, the format set, the OCR gate); this is
the entities, the rules, the factory, the reader and the verbs. The screen is phase 3 (0.10.0).
Schema version 2 to 3.

### Added
- **Seven entities** (`schema/definitions.py`): `control_structure` (name, slug, system, description,
  source, status Draft / Reviewed / Baselined, revision) and its parts `cs_controller` (key, name,
  kind, responsibility, process_model_title, note), `cs_algorithm` (controller, code, name),
  `cs_process_model_entry` (controller, heading, control_actions, variables, updated_by, references),
  `cs_edge` (key, kind, source, target), `cs_signal` (edge, signal_id, kind, name, placeholder) and
  `cs_note` (text, attached_to). Every part names its structure by slug and its parent by key, so the
  rows survive any export and import (a workbook sheet carries no id column) and a later STPA step can
  point at a controller by key and a signal by its id. One sheet each in the workbook (`CS
  structures` ... `CS notes`); the JSON dump carries them with every other entity. Lookups
  `cs_status`, `cs_controller_kind` (asi_escher's `CONTROL_NODE_KINDS`) and `cs_edge_kind`.
- **`FieldType.JSON`** (`schema/fields.py`): a JSON array in a text column, read back as a list
  (`coerce_list`: a list as it is, a JSON array parsed, any other text one item per line, blank is the
  empty list), written as JSON text in a workbook cell, edited one item per line in a form
  (`gui/widgets.py` `ListWidget`). The idea of the people lists of asi_kletz 0.19.0.
- **The service rules** (`services/control_structure_service.py`, one `EntityService` subclass per
  entity, chosen by `service_class`, so they hold on every verb that writes a row): a part names a
  structure and a parent that exist; a controller's key (from its name when not given) and an edge's
  key (the next free `eN`) are unique within the structure and immutable while rows point at them; a
  signal's kind defaults to its edge's and must match it; an edge cannot change kind under its
  signals; a signal id is unique within the structure, a refusal when typed and a warning when a
  dataset is loaded whole (the owner's structure carries a few inherited duplicates; `cs validate`
  repeats them); a control action pointing up the hierarchy (the controllers' `order`) or feedback
  pointing down is a warning, never a refusal; a structure with parts, a controller with dependants
  (its algorithms, process-model entries, the edges touching it and their signals; a note attached to
  it stays, detached) or an edge with signals is deleted with `cascade` or refused; the structure's
  slug is unique and immutable while parts exist. `EntityService` gained the hooks `check`,
  `before_delete` and `after_change` and `delete(..., cascade=)`; `SqlRepository.delete_where`.
  `ControlStructureService` (`brain.control_structures`): `resolve` by id, uid or slug, `parts`,
  `dataset` (the plain form), `create_from_dataset` (one transaction, audited once as `cs.new`),
  `validate`, `delete`, `duplicate` (a deep copy under a new slug, status Draft, revision 1, audited as
  `cs.duplicate`). Events: `cs.changed` (structure, entity, action, id, actor) after every change, one
  for a dataset loaded whole; `cs.exported` after an export.
- **The factory** (`stpa/factory.py`, `brain.factory`): `ControlStructureFactory` with a registry of
  builders, each `(brain, options) -> dataset` with an availability check: `blank`,
  `template:wheel_loader_master` (reads `<control_structures_dir>/wheel-loader/datasets/`; listed as
  unavailable with the reason when absent), `from_drawio`, `from_datasets`, `clone`;
  `register_builder` adds one; `catalog()` for a window's "New from". `to_diagram(structure)` is the
  one place rows become an `asi_escher.Diagram` (`control_structure` kind): a controller a box of its
  kind with its algorithms as `(code, name)` and its process model as `(title, entries)`, an entry
  drawn `- heading: variables; updated by ...` (the dash is how the reader tells one entry from the
  wrapped rest of the previous one); an edge a control action or feedback with its signal lines
  `CA-01 Mission data` in order; a note attached to its controller. `export(structure, out, formats,
  ocr=True)` calls `asi_escher.build` with `provenance=True` and the OCR gate on, under
  `catch_warnings` as `generate/figures.py` does, and returns the files written, `size`, `nodes`,
  `edges`, `issues`, `layout_issues`, escher's `ocr` report and `ocr_verdict`; audited as `cs.export`.
- **The draw.io reader** (`stpa/drawio_reader.py`, standard library only): the owner's
  `control_structure_to_datasets.py` ported (containers by geometry, the Responsibility box, the
  process-model box with its bullets, the `V1 — Name` algorithm boxes, free notes to the nearest
  controller, `CA-02/03/04` expanded, kinds from the style or a `kinds` map) and, for a file
  escher wrote (`host="asi_escher"`), the box's HTML sections read back exactly: the responsibility by
  the greedy-wrap rule, the algorithms by their codes, the entries by their dashes.
  `read_dataset_folder` reads the six envelope files (`id` to `key` or `code`, `controller_id` to
  `controller`, `edge_id` to `edge`, stray `items` kept as variables, a signal without an id skipped
  with a warning, a `mixed` edge taking its first signal's kind).
- **The `cs` verb** (`commands/cs.py`): `list | get <id> | builders | new <builder> [--name --slug
  --system --from <file>] | duplicate <id> --name [--slug] | delete <id> [--cascade] | validate <id>
  | import <drawio-or-folder> | export <id> [--out <dir>] [--format drawio|png|svg]... [--all]
  [--no-ocr]`; a structure by id, uid or slug; the default formats `drawio` and `png`; without
  `--out` the files go to `control_structures/` under the out folder. Every answer a JSON `Result`,
  every issue of an export repeated as a warning, `validate` with `ok` false when a rule is broken.
  The generic `delete` takes `--cascade`.
- **Configuration**: `control_structures_dir` in `dewey.toml` (a path, relative to the file;
  default `../asi_standards/control-structures` beside the working directory;
  `$ASI_DEWEY_CONTROL_STRUCTURES` overrides it); `status` reports it as `control_structures_dir`.
- `tests/fixtures/dewey-0.8.4.db`: a small 0.8.4 database for the migration test.

### Changed
- **Schema version 3.** A 0.8.x database opens with the seven tables created, nothing altered, no
  row touched; the 0.7.4 fixture test counts them. The Dashboard tiles the structures and not the
  six part entities (`gui/dashboard.py` `UNTILED`); the seven are in `HIDDEN_ENTITY_SCREENS` until
  their screen (0.10.0), so the window keeps its ten screens.
- The dispatcher checks a repeatable argument's `choices` item by item (`--format svg --format
  drawio` was refused as a list).
- `uv.lock` takes asi_escher 0.2.0 (the `control_structure` kind, `to_drawio`, `FORMATS`,
  `DEFAULT_FORMATS`, the OCR gate), asi_gutenberg 0.9.0 and asi_hopper 0.1.9, what their checkouts
  declare.

### Tests
- 200 to 222. `test_control_structures.py`: a synthetic eight-box structure with invented names built
  through the factory; the JSON field; every rule and refusal; the direction warning; duplicate
  signal ids as warnings; cascade delete of a controller, an edge and a structure, with the
  refusals; duplicate and the clone builder; validate on rows broken behind the service; every `cs`
  verb and the command line; the export writing drawio and png by default with the OCR gate
  monkeypatched to "competent" (the expected labels, the provenance, the audit and the event,
  `--all`, `--no-ocr`, an unreadable label and an unavailable engine as issues and warnings); one
  real-engine test skipped where the engine is absent; the round trip draw.io to rows to draw.io
  (the same rows, the controllers' order the layout's); `to_diagram`; the hand-drawn reader on a
  synthetic file; `from_datasets` and the template builder on a synthetic envelope folder, through
  the environment and through `dewey.toml`; dump/load and the workbook round trips; the 0.8.4
  migration; the hidden screens and the one tile; a local-only smoke test on the private datasets
  (counts and files only, skipped elsewhere). The existing tests count sixteen entities and the
  seven sheets. The suite points `$ASI_DEWEY_CONTROL_STRUCTURES` at an absent folder.

## [0.8.4] - 2026-10-29

The family's integration review of 2026-10-29. No behaviour changes; schema version unchanged (2).

### Changed
- `uv.lock` follows the siblings: asi_escher 0.1.1 to 0.1.3, asi_gutenberg 0.6.0 to 0.7.1, asi_hopper
  0.1.6 to 0.1.7 (what their `main` branches declare, which is what CI checks out). Every name Dewey
  imports from them (`Diagram`, `LayoutWarning`, `THEME`, `build`; `Document`, `build`; `Hopper`,
  `LIST_FIELDS`, `AuthRequired`, `GatewayError`, `HopperError`) exists unchanged at those versions; the
  additions (`fill_docx`, the Confluence verbs, `WriteSideClosed`) are not called here, and
  `tests/test_jira.py` replays asi_hopper 0.1.7's fixture index as before.

## [0.8.3] - 2026-10-29

A broken-windows sweep of 2026-10-29: the wheel-over-a-combobox hazard asi_kletz 0.15.2 fixed
the same day, found here by inspection before anyone lost a row. Schema version unchanged (2).

### Fixed
- **The mouse wheel over a combobox picked its next value** (`gui/main_window.py`): Tk 8.6 binds
  `<MouseWheel>` on the `TCombobox` class to "select the next value", and the form scrolls on the
  same wheel (`ScrollableFrame` binds it on every widget while the pointer is over the form), so
  scrolling the form with the pointer passing over a task class, a link class or a use-case field
  silently changed it, and the next Save stored it. The window drops that class binding (and the
  spinbox's) once, right after the theme is applied: the wheel scrolls, a value changes only by a
  pick or a keystroke. Same fix as the sister tool, by convention, not shared code.

### Removed
- `issues_to_strings` in `generate/figures.py`: a two-line helper the integration plan sketched
  that nothing ever called; the issue dicts `build_diagram` returns carry `message` themselves.

### Tests
- `test_mouse_wheel_over_a_combobox_never_picks_a_value`: wheels twice over the task-class box of
  a selected row and reads the form back unchanged, then puts Tk's stock binding back to show the
  same wheel moves the value.

## [0.8.2] - 2026-10-29

The owner, 2026-10-29: "change the colour of the little widget that you pull up and down or side to
side to interact with a scroll bar."

### Changed
- **The scrollbar thumb** (`gui/theme.py`, the grid recipe): `TScrollbar` `background`, `lightcolor`
  and `darkcolor` are the palette's `primary_dim` (they were the panel colour, the same as the
  trough's neighbours, so the thumb was hard to find), and `active` maps to `primary`; the trough
  stays `bg`, the arrows as before. Implemented the same way in the sister tool: a convention, not
  shared code.

### Tests
- `test_scrollbar_thumb_is_the_primary`.

## [0.8.1] - 2026-10-28

The JIRA Live Data screen is gone from the window, by the owner's instruction of 2026-10-28.
The instruction was "remove the jira live data screen from dewey". Nothing of the command line
changed: `jira live` and `jira comments` still run through asi_hopper and still answer the same
`Result`, because they were never the screen's; the screen was one client of them, and the
`jira_ticket` cache that `jira sync` feeds, the Dashboard's Open Jira tickets table and every
automation endpoint stay. Schema version unchanged (2).

### Removed
- **The `jira_live` screen** (`gui/jira_live_screen.py`), its registration in
  `build_default_screens`, its `View` entry and its place in the navigation list (second since
  0.5.0): the window has ten screens again, Dashboard first, then the seven entity screens,
  Export / Import, Generate. `POST /screen {"show": "jira_live"}` is now `ok: false, unknown
  screen` like any other unknown key, and `GET /screens` no longer lists it.
- **The comments window** (`gui/jira_comments_window.py`, opened only from that screen),
  `MainWindow.open_comments` and `comment_windows`, and `MainWindow.jira_live` (the fetch kept
  for the session).
- **The worker-thread machinery that existed only for those fetches**: `WorkerFetch` and
  `POLL_MS` in `gui/screens.py`, `MainWindow.execute_quiet`, `run_quiet` and `report_quiet`
  (`run` reports its own Result now). Every verb the window runs is on the Tk thread again.
- **The Dashboard's Jira tile no longer opens anything** (`TILE_TARGETS` removed): like the
  Safety Plan tile it counts the cached rows and is not clickable, because `jira_ticket` is a
  `HIDDEN_ENTITY_SCREENS` entity with no screen.
- **`jira_live_autofetch`** (`dewey.toml`, 0.7.3 to 0.8.0): the key is ignored, with every other
  unknown key; `dewey.example.toml` drops it. `jira_live_jql` stays: it is what `jira live` fetches.

### Changed
- **Plan 3.1 clarified, so Dewey and Kletz read it the same way.** `load_rows` in merge mode, a
  file row whose uid is unknown but whose id matches a stored row: the row now takes the file's
  uid (0.8.0 kept the stored one and warned, listed there as a deviation), with a warning that
  names old and new (`fact 2 takes the file's uid … (was …)`). This is the one deliberate identity
  reconciliation: a Kletz dump merged into Dewey hands the cached `safety_plan_row` rows Kletz's
  uids, as the plan intends. The unique index never trips: a file uid another row already holds
  is matched by uid first and the id is not consulted. `update` stays immutable. A workbook sheet
  carries no `id` column (`map_columns` maps schema fields only), so for a workbook the
  reconciliation is `--mode replace`, which keeps the sheet's uids.
  `test_merge_by_id_adopts_the_file_uid_and_warns`; the Kletz-sheet test now starts from a cached
  row with a Dewey uid.
- `MainWindow._on_event` still returns for `jira.live` (a forwarded `jira live` changes no row)
  and the docstrings of `commands/jira.py`, `services/jira_service.py` and `gui/screens.py` no
  longer name a window. `docs/jira-live-data-plan.md` says the screen was removed; asi_kletz
  keeps its window and the row convention of that plan's section 3.1 is unchanged.

### Tests
- 215 → 198. The live-screen and comments-window tests of `test_gui.py` (stubbed fetches, filters,
  sorting, muted rows, the worker thread, the Comments column, the comments windows, their column
  fit) are gone; the navigation, View menu, nav list, dashboard tile and screen-walk assertions
  count ten screens; `test_jira_live_event_does_not_refresh_screens` stays. `test_core.py`:
  `jira_live_autofetch = true` in `dewey.toml` is ignored. New: `test_jira_live_is_no_longer_a_screen`
  (`test_server.py`): not in the factory, `show` raises `NotFound`, `/screen` answers unknown
  screen, `/screens` lists Dashboard then Tasks, and `jira live` through `/execute` is still a verb.
  `test_jira.py` (the verbs on Hopper's replay fixtures) is untouched.

## [0.8.0] - 2026-10-28

Every row of every entity carries a hidden `uid`, and no table shows `id` or `order`.
The convention is shared with asi_kletz by name, never as code (`docs/hidden-identity-plan.md`,
section 3.1), decided by the owner on 2026-10-28. Schema version 1 → 2: a 0.7.x `dewey.db` opens
as 0.8.0 with every row identified and nothing else changed.

### Added
- **`uid` on every entity**: the last field, `FieldType.TEXT`, header `uid`, `hidden=True`, the
  canonical lowercase UUID4 with dashes (`new_uid`, `UID_PATTERN`, `normalise_uid` in
  `schema/fields.py`). `EntityService.create` assigns it once; `update` with another value fails
  with `uid is immutable` (the same value is a no-op); a second row with the same uid is refused
  by the unique index `ix_<table>_uid` (`ensure_schema`) and reported as `uid … is already used by
  another row`, a `Result`, not a crash. Coercion accepts the canonical form, normalises upper
  case and braces, and rejects anything else naming the field (`uid: 'nope' is not a uid …`).
- **`FieldSpec.hidden`** and **`EntitySchema.visible_fields`**: a hidden field has no widget, no
  column, no `fit_columns` candidate and no place in a diagram (`schema_map` counts visible
  fields); it is written to and read from every file. Only `uid` is hidden.
- **Stamped on open**: `Storage.stamp_uids`, called by `Brain.__init__` right after `ensure_schema`
  and reported as `brain.migration["uids_stamped"]`, gives every row whose uid is NULL or empty a
  fresh one, one `UPDATE … WHERE id = ?` per row in one transaction, `updated_at` untouched,
  audited as `stamp_uids` with the count (actor `system`) once per table that had rows to stamp.
  A second open stamps nothing and audits nothing.
- **In files**: the JSON dump carries `uid` like any field; the workbook writes it as the last
  column of every sheet, headed `uid`, with `column_dimensions[letter].hidden = True`, so the
  sheet reads as before and still round-trips; the import maps it by header like any field.
  `load_rows` matches by uid first, in every mode: a row whose uid is in the table updates that
  row whatever its id in the file; otherwise, in merge mode, a row whose id exists updates that
  row by id and keeps the stored uid (a warning names the uid the file had, when it had one);
  otherwise the row is inserted keeping the file's uid when it has one (and its id in merge mode),
  with a fresh uid when it has none (a 0.7.x file). `replace` wipes first and keeps the file's
  uids. So a Kletz dump or workbook imported here gives the cached `safety_plan_row` rows Kletz's
  uids, and a later import of a newer dump updates them in place instead of duplicating them.
- **A uid where an id is expected**: `get`, `update` and `delete` take a `ref` (argument type
  `ref`): all digits is an id; a uid, in any case, with or without braces, is resolved through
  `EntityService.resolve` and `SqlRepository.get_by_uid`; an unknown uid is `NotFound`
  (`fact uid … not found`); anything else is `neither an id nor a uid`. The automation server's
  `POST /execute` runs the same verbs through the same dispatcher, so an agent can send
  `{"verb": "get", "args": {"entity": "task", "id": "<uid>"}}`. `list --filter uid=…` works as it
  does for any field.
- `tests/fixtures/dewey-0.7.4.db`: a small 0.7.4 database (two facts, one link, one QMS
  document) made with the 0.7.4 code for the open-and-stamp test; `.gitignore` admits
  `tests/fixtures/*.db`.

### Changed
- **The seven entity screens show no `id` and no `order` column.** `EntityScreen.columns` is the
  entity's visible fields minus `order`, with the `MAX_FLAG_COLUMNS` rule as before. The tree
  iids are still the ids, `order` stays editable in the form and stays the default sort, and the
  status bar still says `Fact 2 selected`. The details frame names the row: `Fact details · row 2`
  once a row is selected, `Fact details · copy of row 2` after Duplicate, `Fact details` after
  New. The Dashboard tables were verified against plan 3.3: none had an `id` or `order` column
  (`gui/dashboard.py`), and the Recent changes table keeps `entity_id`, which is the trace of a
  change, not a vestige. JIRA Live Data is unchanged: the Jira key is its identity.
- The form skips hidden fields; `WidgetFactory.create` raises `ValueError` for one.
- `load … --mode append` of a file whose rows the table already knows by uid updates them instead
  of inserting copies (the rule above); a file without uids appends new rows as before.
- `SCHEMA_VERSION = 2`; the registry fingerprint changes, so `schema_migrations` gains a row on
  the first open of an existing database.

### Fixed
- The compare links at the foot of this file lacked `[0.7.4]`.

### Deviations from the plan (`docs/hidden-identity-plan.md`)
- **Where `uid` is declared.** The plan puts it on each of the nine entities in
  `schema/definitions.py` (sections 4 and 5). It is appended by `EntitySchema.__post_init__`
  instead (`uid_field()` in `schema/fields.py`): an entity registered by a caller, as in the
  README's "Adding an entity", carries it too and cannot forget it. A declaration that names
  `uid` must put it last, hidden, as `TEXT`, or it is a `ValueError`. Section 3.1 is unchanged.
- **The audit of `stamp_uids`.** The plan says "audited once per table"; the entry is written only
  for a table that had rows to stamp, otherwise a fresh database and every later open would write
  nine empty entries. The plan did not name the actor; it is `system`.
- **The server's row endpoints.** The plan (sections 3.1, 4 and 5) has them take the same `ref`.
  The server has no row endpoints: `POST /execute` runs the dispatcher, so the change to `get`,
  `update` and `delete` covers it. `automation/server.py` is untouched;
  `test_execute_resolves_a_uid_where_an_id_is_expected` pins the behaviour.
- **Merge by id with a foreign uid.** The plan is silent on a file row whose uid is unknown but
  whose id exists (merge mode). The row is updated by id, the stored uid is kept (it is
  immutable) and the load reports a warning naming the uid the file had.
- **`schema_map`** counts visible fields (`generate/diagrams.py`), following section 3.2; the file
  is not in the plan's section 5 list.
- **The details title after Duplicate** says `… · copy of row 2`, an extension of section 3.3's
  `Task details · row 2`, so the source of the copy stays on screen until it is saved.

### Tests
- 198 → 215. `test_schema.py`: every entity ends with a hidden `uid`, a declared `uid` must be
  last/hidden/TEXT, coercion. `test_core.py`: `create` assigns or keeps, `update` refuses, two rows
  cannot share, `get_by_uid` and `resolve`, and the fixture database opened by 0.8.0 (columns,
  unique indexes, every row stamped, counts audited, nothing else changed, a second open stamps
  nothing). `test_transfer.py`: 64 headers with a hidden last `uid`, export → import keeps every
  uid, a dump with the ids shifted by 100 merges as updates and 0 inserts, a 0.7.x dump without
  uids, merge by id keeps the stored uid and warns, a Kletz-shaped plan sheet. `test_cli.py` and
  `test_server.py`: a uid where an id is expected. `test_gui.py`: no table on any screen has an
  `id`, `order` or `uid` column, each entity screen's columns, the form, the details title.

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

[Unreleased]: https://example.invalid/asi-dewey/compare/v0.8.4...HEAD
[0.8.4]: https://example.invalid/asi-dewey/compare/v0.8.3...v0.8.4
[0.8.3]: https://example.invalid/asi-dewey/compare/v0.8.2...v0.8.3
[0.8.2]: https://example.invalid/asi-dewey/compare/v0.8.1...v0.8.2
[0.8.1]: https://example.invalid/asi-dewey/compare/v0.8.0...v0.8.1
[0.8.0]: https://example.invalid/asi-dewey/compare/v0.7.4...v0.8.0
[0.7.4]: https://example.invalid/asi-dewey/compare/v0.7.3...v0.7.4
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
