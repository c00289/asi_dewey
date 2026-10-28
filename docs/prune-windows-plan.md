# ASI Dewey — Plan: prune the Jira and Safety Plan windows

**Status:** Implemented 2026-10-27 (asi_dewey 0.4.0); deviations recorded by the implementing agent in the CHANGELOG entry
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_dewey 0.4.0 (after the family palette 0.3.0, before the JIRA Live Data
window 0.5.0; see the version ladder in the family document)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md).
**Sister plan:** [asi_kletz/docs/all-columns-plan.md](../../asi_kletz/docs/all-columns-plan.md).
The 0.4.0 pair: Kletz shows every Safety Plan column, Dewey stops showing the Safety Plan at all.

---

## 1. The ask

Asked by the owner on 2026-10-27:

1. **Remove the Jira window** from Dewey. The `JIRA` entry in the navigation list opens a
   generic table-plus-form over the `jira_ticket` cache; it is not the live view the owner wants,
   and that view arrives in 0.5.0 as `JIRA Live Data` with its own plan.
2. **Remove the Safety Plan window** from Dewey. Kletz has owned the Safety Plan since the
   2026-10-27 split; Dewey's `Safety Plan` screen is a second, weaker editor of the same data.
   Its twin, the `Safety Plan Matrix` screen, goes with it for the same reason: one tool edits
   the plan, and that tool is Kletz.
3. **Windows only.** The `jira_ticket` and `safety_plan_row` entities stay, with their tables,
   workbook sheets, `dump` / `load`, the `jira` verb (`sync`, `status`, `get`), the dashboard
   tile "Open Jira tickets", and the diagram and document catalogs that read them.
4. **A declarative exclusion**, not a hand edit of the loop that builds the screens.

## 2. What exists today (verified 2026-10-27: the tree before 0.4.0, with the screens this plan removes)

| Fact | Where |
|---|---|
| `build_default_screens(brain)` registers `dashboard`, then `entity:<name>` for every schema in `brain.registry` in registration order (title = `schema.sheet`), then `safety_plan_matrix` ("Safety Plan Matrix"), `transfer`, `generate`. Thirteen screens in nav order: dashboard, task, fact, machine_function, use_case, link, jira_ticket ("JIRA"), qms_document, person, safety_plan_row ("Safety Plan"), safety_plan_matrix, transfer, generate. | `gui/screens.py` lines 94-111; `schema/definitions.py` lines 100, 168, 194 |
| `ScreenFactory` maps key to `(title, builder)`; `items()`, `title()`, `__contains__`; `create()` raises `NotFound` for an unknown key. | `gui/screens.py` lines 63-91 |
| The View menu, the navigation `Listbox`, and the index arithmetic in `show()` and `_on_nav()` are all derived from `self.factory.items()`. `set_theme()` rebuilds menu and body from the same factory. The first screen is `dashboard` when the factory has it. | `gui/main_window.py` lines 62, 77-78, 129-130, 168-172, 180, 217-232 |
| `SafetyPlanMatrixScreen` lives in `gui/matrix_screen.py` (FIXED columns + one flag group, click toggles through `update`). Its only import is `gui/screens.py` line 98. No other module, test or script imports it (grep over `src`, `tests`, `*.ps1`, `docs`). | `gui/matrix_screen.py`; `gui/screens.py` line 98 |
| The dashboard builds one tile per schema in `brain.registry` and binds click on every tile to `window.show(f"entity:{schema.name}")`; hover swaps the tile style. The lower "Open Jira tickets" table is filled by `open_jira_tickets()`, which lists the `jira_ticket` entity with `status = open`. | `gui/dashboard.py` lines 21-31, 37, 72; `services/queries.py` lines 18-19 |
| `EntitySchema` is a frozen dataclass (`name`, `table`, `label`, `sheet`, `fields`, `order_by`, `description`). `to_dict()` is its serialisation: it feeds `SchemaRegistry.fingerprint()`, which is stored in `schema_migrations` (a changed fingerprint inserts a new row on the next open) and reported by the `schema` verb. | `schema/entity.py` lines 15-26, 106-115; `schema/registry.py` lines 45-50; `storage/sqlite.py` lines 121-127 |
| Nine registered entities; `tests/test_schema.py` asserts `len(default_registry) == 9` and, in `test_safety_plan_matrix_fields_are_unique_and_grouped`, the 63 fields and the group sizes of `safety_plan_row`. That test reads the registry, not a screen. | `schema/definitions.py` line 194; `tests/test_schema.py` lines 65, 68-75 |
| `gui/entity_screen.py` has `MAX_FLAG_COLUMNS = 8` and drops every flag column from the table when a schema has more than eight flags; the form still shows every field in group boxes. After this plan no entity with flags has a screen. | `gui/entity_screen.py` lines 16, 42-45 |
| `generate/diagrams.py` (`lifecycle_overview`, `phase_flow`) and `generate/documents.py` (`safety_plan`) read `safety_plan_row` rows and the `lifecycle_phase` lookup; `status_report` reads `open_jira_tickets()`. They are commands, not screens. | `generate/diagrams.py` lines 22, 46-58, 92; `generate/documents.py` lines 83-140, 170-180 |
| `gui/generate_screen.py`, `gui/transfer_screen.py`, `commands/gui.py`, `gui/app.py`: no `show()` of any removed key. `main_window.py` shows only `transfer`, `generate`, `dashboard`. | grep `show(` over `src/asi_dewey` |
| Tests touching the removed screens: `tests/test_gui.py` line 43 (`"safety_plan_matrix" in keys`), lines 97-103 `test_safety_plan_form_has_groups` (opens `entity:safety_plan_row`), lines 105-115 `test_matrix_toggle_and_group_switch` (opens `safety_plan_matrix`). `test_widget_factory_round_trips` (lines 140-165) takes `plan.field("loc_dms")` from the registry and needs no screen. `test_pick_theme_repaints_and_latches` (lines 299-320) shows every key of `factory.items()`. | `tests/test_gui.py` |
| The `seeded` fixture creates one `safety_plan_row` and no `jira_ticket`; the dashboard tile for `safety_plan_row` therefore reads `1`. | `tests/conftest.py` lines 43-47 |
| Docs that name the removed screens: `README.md` line 36 ("a Safety Plan Matrix where a click toggles a flag") and line 297 (Layout: "entity/matrix/dashboard/transfer/generate screens"); `docs/plan.md` line 211 (section 8, "Safety Plan matrix (grid with reviewer checkboxes)") and line 261 (section 10, phase 5); `CHANGELOG.md` line 136 (the 0.1.0 entry, history). No screenshots exist in the repo. | `README.md`, `docs/plan.md`, `CHANGELOG.md` |
| Versions: `version.py` and `pyproject.toml` say 0.3.0; `CHANGELOG.md` has `[0.3.0]` and an `[Unreleased]` block whose first heading still reads "Planned for 0.3.0" (the family lock, now 0.6.0 on the ladder). The family document's version table says 0.2.0 for both primary tools; its plans table lists five plans. | `src/asi_dewey/version.py`, `pyproject.toml`, `CHANGELOG.md` lines 7-14, the family document (now `../asi_fusa_tools/ASI_FUSA_TOOLS.md`) lines 7-13, 216-224 |

## 3. Design

### 3.1 The exclusion: `HIDDEN_ENTITY_SCREENS` in `gui/screens.py`

Two mechanisms were on the table: a `screen: bool = True` attribute on `EntitySchema`, or a
constant in `gui/screens.py` that `build_default_screens` consults. The constant is chosen.

Why not the schema attribute:

- `EntitySchema` is "one declaration per table, from which everything else is derived":
  table, model, sheet, JSON shape, command arguments. `to_dict()` is its serialisation and it
  feeds the registry fingerprint, the `schema_migrations` table and the `schema` verb. A window
  preference there either changes the fingerprint for a cosmetic reason (every database would
  get a new migration row at 0.4.0) or has to be kept out of `to_dict()` by hand, which leaves
  the dataclass half-serialised and the `schema` verb lying by omission.
- The theme plan set the precedent for window work: "No change to `schema/` ... Schema version
  stays 1." This plan keeps it.
- The registry pattern is: `SchemaRegistry` catalogs the entities, and each factory decides what
  it derives from the catalog. `build_default_screens` is the `ScreenFactory`'s derivation rule,
  so its exceptions belong beside it. The sister tool already works this way: Kletz's
  `build_default_screens` fixes its screen list in `gui/screens.py` and says so in its docstring.
  Which screens exist is a `gui/screens.py` decision in both tools.

The code:

```python
# Entities that keep a table, commands, a workbook sheet and dump/load but have no window.
# jira_ticket: a cache fed by `jira sync`; the live view is the `jira_live` screen (0.5.0).
# safety_plan_row: the Safety Plan is Kletz's since the 2026-10-27 split.
HIDDEN_ENTITY_SCREENS: frozenset[str] = frozenset({"jira_ticket", "safety_plan_row"})


def build_default_screens(brain: Brain, hidden: frozenset[str] = HIDDEN_ENTITY_SCREENS) -> ScreenFactory:
    unknown = hidden - set(brain.registry.names())
    if unknown:
        raise ValueError(f"HIDDEN_ENTITY_SCREENS names unknown entities: {', '.join(sorted(unknown))}")
    factory = ScreenFactory()
    factory.register("dashboard", "Dashboard", DashboardScreen)
    for schema in brain.registry:
        if schema.name in hidden:
            continue
        factory.register(f"entity:{schema.name}", schema.sheet, lambda m, w, s=schema: EntityScreen(m, w, s))
    factory.register("transfer", "Export / Import", TransferScreen)
    factory.register("generate", "Generate", GenerateScreen)
    return factory
```

`hidden` is a keyword argument so a test can build a factory with another set; nobody else
passes it. A name that is not a registered entity is a `ValueError` at build time, so a typo
cannot hide nothing in silence. Nav order after the change, ten screens: dashboard, task, fact,
machine_function, use_case, link, qms_document, person, transfer, generate.

### 3.2 The matrix screen is deleted

The `factory.register("safety_plan_matrix", ...)` line and the import of
`SafetyPlanMatrixScreen` go; `gui/matrix_screen.py` is deleted. Nothing else imports it
(section 2). `flag_fields` in `schema/entity.py` keeps its docstring "(Safety Plan matrix)":
it describes the sheet's matrix of flag columns, not the screen.

### 3.3 The View menu and the navigation list follow

Both are derived from `factory.items()` and need no edit. `show()` on a removed key raises
`NotFound` exactly as for any unknown key; the automation server's future `screen open`
command inherits that behaviour. `set_theme()` rebuilds from the same factory, so a repaint
cannot bring a removed screen back. The File menu is unchanged.

### 3.4 The dashboard: nine tiles, two of them not clickable

The "Rows per entity" tiles stay for all nine entities: the counts are the dashboard's job and
`status` reports the same numbers. A tile whose `entity:<name>` key is not in
`self.window.factory` gets no click and no hover binding and keeps the plain `Tile.TFrame`
style; the other seven behave as today. One guard in the tile loop:

```python
key = f"entity:{schema.name}"
if key in self.window.factory:
    ... bind <Button-1>, <Enter>, <Leave> as today ...
```

The box title stays "Rows per entity (click to open)". The lower "Open Jira tickets" table,
`tasks_due` and `recent_changes` are untouched.

### 3.5 What stays, named

- Entities `jira_ticket` and `safety_plan_row`: schema, table, `SCHEMA_VERSION = 1`, the
  registry fingerprint, the `JIRA` and `Safety Plan` sheets of the workbook, `dump` / `load`,
  `export` / `import`, every CRUD verb.
- Verb `jira` with `sync`, `status`, `get`; `services/jira_service.py`; the `jira.synced` event.
- Dashboard "Open Jira tickets" and the nine count tiles.
- Diagram and document catalogs: `lifecycle_overview`, `phase_flow`, `safety_plan`,
  `status_report`, `handbook` and their tests.
- `tests/test_schema.py::test_safety_plan_matrix_fields_are_unique_and_grouped`,
  `tests/test_jira.py`, the `seeded` fixture.
- `gui/entity_screen.py` and its `MAX_FLAG_COLUMNS` cap. Kletz removes its own cap in
  0.4.0 (sister plan); Dewey's is Dewey's call and no shown entity has flags any more.

### 3.6 Documentation wording

- `README.md`: a "What is in 0.4.0" section ("The JIRA, Safety Plan and Safety Plan Matrix
  screens are gone; the entities, sheets, verbs and the dashboard tile stay; the Safety Plan is
  edited in asi_kletz; the live Jira view follows in 0.5.0"); the 0.1.0 bullet at line 36 gains
  "(the Safety Plan Matrix screen was removed in 0.4.0)"; the Layout line 297 drops `matrix`;
  the version in line 4 becomes 0.4.0.
- `docs/plan.md` section 8: the "Special screens" bullet becomes "Dashboard (counts, open Jira,
  this week's tasks), Export / Import, Generate; `HIDDEN_ENTITY_SCREENS` in `gui/screens.py`
  names the entities that have no screen (`jira_ticket`, `safety_plan_row`, 0.4.0)"; section 10
  gains phase 8 "Prune windows (0.4.0)"; section 12 gains a dated line.
- `CHANGELOG.md`: a `[0.4.0] - <date>` entry with `Removed` (the three screens,
  `gui/matrix_screen.py`) and `Changed` (`build_default_screens` skips
  `HIDDEN_ENTITY_SCREENS`; dashboard tiles without a screen are not clickable; tests). While
  there, the stale `[Unreleased]` heading "Planned for 0.3.0" (the family lock) becomes
  "Planned for 0.6.0" to match the ladder; the single-instance plan carries its own retarget.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Exclusion + tests | `HIDDEN_ENTITY_SCREENS`, the `hidden` argument and the unknown-name check in `build_default_screens`; the `safety_plan_matrix` registration and import removed; `gui/matrix_screen.py` deleted; the dashboard tile guard; `tests/test_gui.py` updated as in section 6. | `uv run pytest` and `uv run ruff check src tests` clean; `[k for k, _ in window.factory.items()]` is the ten-key list of section 3.1; `grep -r matrix_screen src tests` is empty. |
| 2. Docs | README "What is in 0.4.0", the 0.1.0 note, Layout line; CHANGELOG `[0.4.0]` and the Unreleased heading; `docs/plan.md` sections 8, 10, 12; `version.py` and `pyproject.toml` 0.4.0. | `asi-dewey-gui --version` prints 0.4.0; the window title and the nav brand say 0.4.0; no doc in the repo describes a JIRA or Safety Plan screen as present. |
| 3. Family | Family document: version table row for `asi_dewey` reads 0.4.0 and its role text no longer lists "the safety plan matrix" as something Dewey shows (the entity stays; the wording becomes "a cached copy of the safety plan, edited in asi_kletz"); plans table gains this plan and the sister plan. | The family file names both 0.4.0 plans; `tests/test_theme.py` still finds the palette digest in it; tag left to the owner. |

## 5. Files touched

```
src/asi_dewey/gui/screens.py               HIDDEN_ENTITY_SCREENS; `hidden` argument; skip in the loop; matrix import and registration removed
src/asi_dewey/gui/matrix_screen.py         deleted
src/asi_dewey/gui/dashboard.py             tile click/hover bound only when `entity:<name>` is in window.factory
tests/test_gui.py                          nav-order assertion; two screen tests removed; new absence test (section 6)
README.md                                  "What is in 0.4.0"; 0.1.0 note; Layout line; version
CHANGELOG.md                               [0.4.0] entry (Removed / Changed); Unreleased heading retitled 0.6.0
docs/plan.md                               section 8 (screens), section 10 (phase 8), section 12 (change log)
src/asi_dewey/version.py, pyproject.toml   0.4.0
../asi_fusa_tools/ASI_FUSA_TOOLS.md                           version table (0.4.0, role text), plans table (both 0.4.0 plans)
```

Not touched: `schema/` (no `screen` attribute, `SCHEMA_VERSION` stays 1, fingerprint
unchanged), `storage/`, `repositories/`, `services/` (including `jira_service.py` and
`queries.py`), `commands/` (including `jira.py`), `io/`, `generate/`, `gui/entity_screen.py`,
`gui/main_window.py`, `gui/generate_screen.py`, `gui/transfer_screen.py`, `gui/theme.py`,
`gui/palettes.py`, `tests/test_schema.py`, `tests/test_jira.py`, `tests/test_generate.py`,
`tests/conftest.py`, `dewey.example.toml`, `uv.lock`.

## 6. Tests

**`tests/test_gui.py`**

- `test_navigation_and_dashboard` (line 41): the assertion on line 43 becomes an exact
  nav-order check, `keys == ["dashboard", "entity:task", "entity:fact", "entity:machine_function",
  "entity:use_case", "entity:link", "entity:qms_document", "entity:person", "transfer", "generate"]`;
  the rest of the test (dashboard first, `fact` tile reads `2`, `show("entity:fact")`) stays.
- `test_safety_plan_form_has_groups` (lines 97-103): **deleted**. It opened
  `entity:safety_plan_row`, which no longer exists; after this plan no entity with a screen has
  flag groups, so there is no other entity to re-point it at. Flag widgets stay covered by
  `test_widget_factory_round_trips`, which builds them from the registry.
- `test_matrix_toggle_and_group_switch` (lines 105-115): **deleted** with the screen. Toggling
  a flag through `update` is a command path covered by `tests/test_core.py`; the dashboard
  count for `safety_plan_row` is asserted in the new test below.
- New `test_pruned_screens_are_absent(window, seeded)`:
  - `from asi_dewey.gui.screens import HIDDEN_ENTITY_SCREENS`;
    `HIDDEN_ENTITY_SCREENS == frozenset({"jira_ticket", "safety_plan_row"})`.
  - `keys = [k for k, _ in window.factory.items()]`; none of `entity:jira_ticket`,
    `entity:safety_plan_row`, `safety_plan_matrix` is in `keys`; none is `in window.factory`;
    `len(keys) == 10`.
  - `with pytest.raises(NotFound): window.show("safety_plan_matrix")` and the same for
    `entity:jira_ticket`; `window.current_key` is still `dashboard` afterwards.
  - View menu: `menubar = window.nametowidget(window.cget("menu"))`; the second cascade is
    `View`; its `command` entries' labels equal `[t for _, t in window.factory.items()]` and
    contain none of `JIRA`, `Safety Plan`, `Safety Plan Matrix`; the last entry is the `Theme`
    cascade (the pattern of Kletz's `test_view_menu_has_a_theme_cascade_and_file_menu_is_unchanged`).
  - Navigation list: `window.nav.size() == 10` and no row of `window.nav.get(0, "end")` contains
    `JIRA` or `SAFETY PLAN`.
  - Entities stay: `"jira_ticket" in seeded.registry and "safety_plan_row" in seeded.registry`;
    `len(seeded.registry) == 9`; `seeded.execute("count", entity="safety_plan_row").data["count"] == 1`.
  - Dashboard: `dash._tile_vars["safety_plan_row"].get() == "1"` and
    `dash._tile_vars["jira_ticket"].get() == "0"`; the tile widget for `safety_plan_row` has no
    `<Button-1>` binding (`tile.bind("<Button-1>") == ""`) while the `fact` tile has one.
- New `test_hidden_set_must_name_registered_entities(seeded)`:
  `build_default_screens(seeded, hidden=frozenset({"unicorn"}))` raises `ValueError`;
  `build_default_screens(seeded, hidden=frozenset())` yields twelve keys including
  `entity:jira_ticket` and `entity:safety_plan_row` (the mechanism, not the policy).
- `test_pick_theme_repaints_and_latches`: unchanged; it loops over `factory.items()` and now
  rebuilds ten screens instead of thirteen.
- `grep` guard in `tests/test_generate.py` style: a one-line test that
  `Path("src/asi_dewey/gui/matrix_screen.py")` does not exist is not worth a test; the import
  line removal is enough, and `ruff` flags an unused import if the registration were left behind.

**`tests/test_schema.py`**: unchanged. `test_registry_aliases_and_fingerprint` (nine entities,
`get("JIRA")`, `get("Safety Plan")`) and `test_safety_plan_matrix_fields_are_unique_and_grouped`
pass as they are, which is the proof that only windows were removed.

**`tests/test_jira.py`, `tests/test_generate.py`, `tests/test_transfer.py`**: unchanged, must
still pass; they exercise the entities and verbs that this plan leaves alone.

## 7. Rejected alternatives

- **Keep the matrix.** It is a faster flag editor than the generic form, and the flags are
  real data in Dewey's database. Rejected: the Safety Plan has one owner since the split, Kletz,
  and Kletz carries the same matrix screen. Two editors of one plan in two databases is the
  drift the split was made to end. Anyone who needs to flip a flag in Dewey's copy can do it
  through `update` or by importing Kletz's workbook.
- **`EntitySchema.screen: bool = True`.** Declarative and close to the entity, but it puts a
  window preference into the object whose serialisation is the schema fingerprint and the
  `schema` verb (section 3.1).
- **Deleting the two entities.** Out of scope by the ask; it is a schema version bump with a
  dump-format change and a workbook change (section 8).
- **Hard-coding the screen list as Kletz does.** Kletz has one entity and a fixed list of four
  screens by design. Dewey's rule is "every entity gets a screen", and the exclusion list keeps
  that rule readable: new entities still appear without an edit.
- **A `hidden_screens` key in `dewey.toml`.** A project setting for what is a product
  decision; it would also make the test suite's screen list depend on a file.
- **Hiding the entries from the navigation list and menu but leaving `show()` working.** Half a
  removal; the automation server would still be able to open a screen the owner asked to remove.

## 8. Open items

- **Removing `safety_plan_row` from Dewey altogether** (a later version, not planned here). It
  would take: dropping `SAFETY_PLAN_ROW` and the five flag tuples from `schema/definitions.py`
  (`ALL_ENTITIES` to eight, `test_registry_aliases_and_fingerprint` to eight); `SCHEMA_VERSION`
  2 with a migration that leaves or drops the `safety_plan` table; the `Safety Plan` sheet leaves
  the workbook and `import` warns on it as an unknown sheet; dump files that carry
  `safety_plan_row` load with the "skipped unknown entity" warning; `pdp_phase` and
  `plan_status` lookups go, `lifecycle_phase` stays if the diagrams keep it; the `safety_plan`
  document and the `lifecycle_overview` and `phase_flow` diagrams are retired or re-pointed
  (Kletz has its own); `tests/conftest.py` `seeded` and `tests/test_generate.py` follow; the
  family document's role text for Dewey changes. Decide after 0.5.0 when the Jira live view
  shows whether Dewey still needs any plan data for `status_report`.
- Whether the two non-clickable tiles should read as such (muted name label, or a "(in Kletz)" /
  "(cache)" caption). Cheap; decide after seeing the dashboard.
- In 0.5.0, whether the `jira_ticket` tile should open the `jira_live` screen. That plan decides.
- Whether `HIDDEN_ENTITY_SCREENS` should appear in the `status` or `schema` verb output so an
  agent can learn which entities have a window. Not now: the automation server's `screen`
  commands are the place for that.

*Written 2026-10-27.*
