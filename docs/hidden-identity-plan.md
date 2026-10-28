# ASI Dewey — Plan: hidden identity (`uid`) and the end of the `id` column

**Status:** Decided 2026-10-28; to be implemented as asi_dewey 0.8.0 (schema version 1 → 2)
**Written:** 2026-10-28
**Owner:** FuSa engineer
**Target version:** asi_dewey 0.8.0
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md). This plan adds one
convention section to the charter ("Identity: `id` and `uid`"), one row to the plans table and one to the
version ladder. The charter is edited by the owner's orchestrating agent once both tools have shipped,
never by the agent implementing this plan.
**Sister plan:** [asi_kletz/docs/hidden-identity-plan.md](../../asi_kletz/docs/hidden-identity-plan.md).
Same convention, implemented twice, never shared as code. The two implementations run in tandem; the
only thing they must agree on byte for byte is section 3.1 (the `uid` value and where a file carries it),
because a Kletz workbook or JSON dump is imported into Dewey, whose `safety_plan_row` rows are a cached
copy of Kletz's plan.

---

## 1. The ask

The owner, 2026-10-28, on every table of both tools:

> it is obviously important that all objects have some internal guid that is not visible but serves for
> traceability; then of course we want to preserve the order of elements in a table; but the leftmost
> columns `order` and `id` are vestigial: `order` was there in case a sorting operation broke order and
> the id is just the order.

Agreed, with one correction the owner accepted: `order` is a position and `id` is the insertion
sequence; `id` cannot be renumbered when a row is inserted, duplicated or re-imported. So:

1. **Every row of every entity carries a `uid`**: assigned once on creation, never shown in a table or a
   form, never changed, carried by every file the tool writes (JSON, workbook) and honoured by every
   import. It is the pointer a document, a sibling or a later database uses to say "this row".
2. **No table shows `id`, and no table shows `order` where an entity has one.** The `id` stays the short
   handle of the command vocabulary (`update task 2 ...`), the row iid of every tree, the audit log's
   `entity_id` and the status bar's "Task 2 selected". An `order` field stays editable in the form and
   stays the default sort; it just has no column.
3. **The order of the elements is preserved** by each entity's `order_by` as today.

## 2. What exists today (verified 2026-10-28, asi_dewey 0.7.4)

| Fact | Where |
|---|---|
| Nine entities (`task`, `fact`, `machine_function`, `use_case`, `link`, `jira_ticket`, `qms_document`, `person`, `safety_plan_row`); every table has `id INTEGER PRIMARY KEY AUTOINCREMENT`, the fields, `created_at`, `updated_at`. `ensure_schema` creates a missing table and adds a missing column with `ALTER TABLE … ADD COLUMN`, then records the registry fingerprint in `schema_migrations`. No data migration step exists. `SCHEMA_VERSION = 1`. | `storage/sqlite.py:84-130`, `schema/definitions.py`, `version.py` |
| `FieldSpec(name, type, label, required, lookup, group, width, help)`; no notion of a hidden field. `coerce_row` rejects unknown fields; `SYSTEM_FIELDS` pass through. | `schema/fields.py:59-66`, `schema/entity.py` |
| `EntityService.create` coerces, inserts, audits, publishes `entity.created`; `update` by `id`. `load_rows(rows, mode)`: `replace` wipes; `merge` upserts **by `id`**; `append` inserts fresh ids; the `id` key is stripped before coercion. | `services/entity_service.py:85-126` |
| JSON dump: `brain.service(name).list()` rows (so `id`, timestamps, every field). Workbook: one column per `schema.fields` entry headed `spec.header`, **no `id` column**; import maps columns by header text in order; the plan sheet asserts 63 headers. | `io/exporters.py:79-145`, `io/importers.py`, `tests/test_transfer.py:45`, `tests/test_schema.py:71` |
| Repository API: `get(id)`, `list(filters, order_by, limit, offset)`, `count`, `exists(id)`, `create(data, row_id=None)`, `update`, `delete`, `delete_all`, `bulk_insert(rows, keep_ids)`. `list --filter key=value` is generic over any field. | `repositories/sql_repo.py`, `commands/crud.py` |
| Tables in the window: **seven entity screens** (`task`, `fact`, `machine_function`, `use_case`, `link`, `qms_document`, `person`; `jira_ticket` and `safety_plan_row` are `HIDDEN_ENTITY_SCREENS`), each `EntityScreen` with `columns = ["id"] + [fields, flags only when ≤ MAX_FLAG_COLUMNS]`, a search, a sort by heading, `cell_text` per column, URL cells clickable since 0.7.4, a form below; the **Dashboard** tables (verify their column tuples in `gui/dashboard.py:55`); **JIRA Live Data** (the Jira key is its identity). | `gui/entity_screen.py:41-97`, `gui/screens.py:209`, `gui/dashboard.py`, `gui/jira_live_screen.py` |
| The form shows every non-group field (`order` included where the entity has one) and the flag groups; `new`, `save`, `duplicate` (clears `order`), `delete` work on `selected_id`. | `gui/entity_screen.py:_build_form`, actions |
| Tests: 198 pass; `test_widget_factory_round_trips` builds widgets per field; the entity-screen tests pin `screen.columns` by index (`_point_at` uses `screen.columns.index(column) + 1`). | `tests/test_gui.py` |

## 3. Design

### 3.1 The `uid` (shared with Kletz, byte for byte)

- **Field.** `uid`, `FieldType.TEXT`, header `uid`, `hidden=True`, the **last** field of every entity. Value:
  the canonical lowercase UUID4 with dashes, 36 characters (`str(uuid.uuid4())`). Validation on coercion:
  when present it must match `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`; a
  value in another case or with braces is normalised to the canonical form; anything else is a
  `ValidationError`.
- **Assigned once.** `EntityService.create` sets `uid` when the row has none. `update` with a `uid` that
  differs from the stored one is a `ValidationError("uid is immutable")`; the same value is a no-op.
  `duplicate` in the window makes a new row, so a new uid.
- **Unique.** `CREATE UNIQUE INDEX IF NOT EXISTS ix_<table>_uid ON <table>(uid)` after the column exists.
- **Stamped on open.** After `ensure_schema`, `Storage.stamp_uids(registry)` gives every row whose `uid`
  is NULL or empty a fresh value, one `UPDATE … WHERE id = ?` per row inside one transaction, audited once
  per table as `stamp_uids` with the count. A 0.7.x `dewey.db` therefore opens as 0.8.0 with every row
  identified and nothing else changed. `SCHEMA_VERSION = 2`.
- **In files.** JSON: the row dicts carry `uid` as they carry every field. Workbook: `uid` is the last
  column of every sheet, headed `uid`, written with `ws.column_dimensions[letter].hidden = True` so the
  sheet reads as before and still round-trips. The import maps it by header like any field.
- **On load.** `load_rows`: a row with a `uid` that exists in the table is an **update of that row**
  (whatever its `id` in the file); otherwise a row with an `id` that exists is an update by `id` (merge
  mode only, as today); otherwise an insert that keeps the file's `uid` when present (all modes) and the
  file's `id` in merge mode. `replace` wipes first and keeps the file's uids. So a Kletz dump or workbook
  imported into Dewey gives Dewey's cached `safety_plan_row` rows Kletz's uids, and a later import of a
  newer dump updates them in place instead of duplicating them.
- **Readable.** `get <entity> <ref>`, `update`, `delete` accept a uid where an id is expected: a `ref`
  that is all digits is an id, a `ref` matching the uid pattern is resolved through `repo.get_by_uid`; an
  unknown uid is `NotFound`. `list --filter uid=…` works as it does for any field. The automation server's
  row endpoints take the same `ref`.

### 3.2 Hidden fields

`FieldSpec.hidden: bool = False`. A hidden field has no widget in the form, no column in any table, no
entry in `fit_columns` candidates, and no place in a diagram or document unless the generator asks for it
by name. It is written to and read from every file. `EntitySchema.visible_fields` is the tuple the window
uses; `fields` stays the full tuple the storage and the transfers use. Only `uid` is hidden in 0.8.0.

### 3.3 The tables

| Table | Today | 0.8.0 |
|---|---|---|
| The seven entity screens (`gui/entity_screen.py`) | `columns = ["id"] + [fields …]` | `columns = [visible fields, minus order, flags as today]`: no `id`, no `order`, no hidden field. The tree iids stay the ids. The `MAX_FLAG_COLUMNS` rule is unchanged. |
| Dashboard tables (`gui/dashboard.py`) | verify | no `id` or `order` column; the audit table (if any) keeps `entity_id`: it is the trace, not a vestige. |
| JIRA Live Data | the Jira key | unchanged |
| The form | every non-group field | every visible non-group field; `order` stays. The details frame's title gains the id: `Task details · row 2`, so the handle a command needs is on screen without a column. |

### 3.4 What does not change

The command vocabulary (`id` positional, now also a uid), the audit log, the events, the family lock,
the automation server's shape, the generate catalog (diagrams and documents read rows by name, never by
`id`), the workbook's visible columns and their order, the JSON shape apart from the new key.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Schema + storage + service | `FieldSpec.hidden`, `EntitySchema.visible_fields`; `uid` as the last field of the nine entities (`definitions.py`); `new_uid()` and `UID_PATTERN` in `schema/fields.py`; coercion and normalisation; `create` assigns, `update` refuses a change; `Storage.stamp_uids` + the unique index in `ensure_schema`; `Brain.__init__` calls `stamp_uids` after `ensure_schema`; `SCHEMA_VERSION = 2`; `repo.get_by_uid`. | `uv run pytest` passes; a copy of a 0.7.4 `dewey.db` opened by 0.8.0 has `uid` on every row of every table, the nine unique indexes, one `stamp_uids` audit entry per table with a count, and no other change (diff of a JSON dump minus `uid`). |
| 2. Files + commands | JSON unchanged apart from the key; workbook `uid` last and hidden; `load_rows` matches by uid first (3.1); `get` / `update` / `delete` and the server's row endpoints resolve a uid `ref`. | Export → import on a fresh database gives the same uids; a dump with the ids shifted by 100 merges by uid as updates, not inserts; a Kletz-shaped plan sheet (63 visible headers plus a hidden `uid`) imports into `safety_plan_row` keeping the uids; `get task <uid>` returns the row; `update … <uid> --set uid=…` fails with `uid is immutable`. |
| 3. Tables + form | 3.3: no `id`, no `order`, no hidden field on any table; the details frame names the row id; `fit_columns` unchanged otherwise; the `_point_at` test helper indexes `screen.columns` as before. | `test_gui.py` passes with the new column sets; no tree in the window has a column named `id`, `order` or `uid` (one test walks every screen); the status bar still says `Task 2 selected`. |
| 4. Docs + version | README ("What is in 0.8.0", the entity-screen paragraph, a short "Identity" paragraph under the Python API section: id is the handle, uid is the trace), CHANGELOG 0.8.0 with any deviation, `version.py` and `pyproject.toml` 0.8.0, `dewey.example.toml` untouched; commit, push, annotated tag `v0.8.0`, GitHub Release with the CHANGELOG section (charter, "Releases and tags"). **No edit to `asi_fusa_tools` or `asi_kletz`.** | `uv run pytest` and `uv run ruff check src tests` clean; the tag and release exist; this plan's Status line says Implemented. |

## 5. Files touched

```
src/asi_dewey/schema/fields.py          FieldSpec.hidden, UID_PATTERN, new_uid, coercion of a uid
src/asi_dewey/schema/entity.py          visible_fields; the immutability check lives in the service
src/asi_dewey/schema/definitions.py     uid last on every entity
src/asi_dewey/version.py                0.8.0, SCHEMA_VERSION = 2
src/asi_dewey/storage/base.py           stamp_uids on the interface
src/asi_dewey/storage/sqlite.py         the unique index in ensure_schema; stamp_uids
src/asi_dewey/brain.py                  stamp_uids after ensure_schema; "uids_stamped" in the migration summary
src/asi_dewey/repositories/sql_repo.py  get_by_uid
src/asi_dewey/services/entity_service.py  create assigns; update refuses; load_rows by uid; resolve(ref)
src/asi_dewey/commands/crud.py          id positional accepts a uid (type "ref")
src/asi_dewey/automation/server.py      the row endpoints take the same ref
src/asi_dewey/io/exporters.py           workbook: uid last and hidden
src/asi_dewey/gui/entity_screen.py      columns = visible fields minus order; details title
src/asi_dewey/gui/dashboard.py          no id / order column
src/asi_dewey/gui/widgets.py            no widget for a hidden field (WidgetFactory.create raises; the form skips)
tests/test_schema.py, test_core.py, test_transfer.py, test_cli.py, test_server.py, test_gui.py
tests/fixtures/dewey-0.7.4.db           a small 0.7.4 database (two facts, one link, one QMS document) for the open-and-stamp test
README.md, CHANGELOG.md, pyproject.toml, docs/hidden-identity-plan.md (Status)
```

## 6. Tests

- **Schema.** Every registered entity ends with `uid`, hidden, TEXT; `visible_fields` excludes it; the
  registry fingerprint changes (so `schema_migrations` gains a row on open). Coercion: canonical uid
  accepted, upper case and braces normalised, `not-a-uid` rejected with the field named.
- **Storage.** A 0.7.4 fixture database opened by 0.8.0: the column and the unique index on every table,
  every row stamped, counts audited, nothing else changed. Opening it twice stamps nothing the second time.
  Two rows cannot share a uid (the index raises; the service reports it as an error, not a crash).
- **Service.** `create` without a uid gets one; `create` with a uid keeps it; `update` changing it fails;
  `get_by_uid`; `resolve("12")` and `resolve("<uid>")`.
- **Transfer.** The plan sheet has 64 headers, the last `uid`, and that column is hidden; export →
  import (replace) on an empty database keeps every uid; a JSON dump with every `id` shifted by 100 merges
  as updates and 0 inserts; a dump without uids (a 0.7.x file) still imports and the new rows are stamped;
  a workbook whose plan sheet carries Kletz's uids gives `safety_plan_row` those uids.
- **Commands and server.** `get`, `update`, `delete` by uid; an unknown uid is `NotFound`; `list
  --filter uid=…`.
- **Window.** No table on any screen has a column named `id`, `order` or `uid`; each entity screen's
  columns are its visible fields minus `order` with the flag rule as before; the form has no `uid` widget
  and still has `order`; the details title names the selected row; selecting, saving, duplicating,
  deleting and the clickable URL cells work as in 0.7.4.

## 7. Risks and decisions

- **Why not a GUID as the primary key.** The integer `id` is typed by people and agents all day; a
  36-character key would be hostile on the command line and in the status bar. Jira has an id and a key
  for the same reason. Decided: `id` handle, `uid` trace.
- **Why `uid` is in the workbook at all when it is hidden.** Without it a workbook edited in Excel and
  imported back cannot say which row it is, and ids are not in the sheet. Hidden column, present data.
- **The cached plan rows.** They get Kletz's uids on the next import of a Kletz dump or workbook (3.1,
  on load). Until then they carry uids of their own; that is correct, they are different rows in a
  different database.
- **Tandem risk.** The two agents must not edit each other's repo or the charter. The orchestrating
  agent adds the charter section and the two table rows after both have tagged.

## 8. Open questions

- Should the Jira ticket cache key rows by the Jira key rather than a uid of its own? No: the Jira key
  is a field, the uid is the row's identity like every other; a later plan may add a unique index on
  the key.
- Should Gutenberg documents print the uid of every row they cite, in a provenance appendix? Owner's call;
  the hidden rule says a document asks for it by name.

## 9. Change log

- 2026-10-28: written, decided; the sister plan written the same day.
