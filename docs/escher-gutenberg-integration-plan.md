# ASI Dewey — Plan: integrate asi_escher (diagrams) and asi_gutenberg (documents)

**Status:** Implemented 2026-10-27 (asi_dewey 0.2.0); see the CHANGELOG entry
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_dewey 0.2.0
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md) (the ontology this plan implements)
**Prerequisite:** [asi_gutenberg/docs/escher-integration-plan.md](../../asi_gutenberg/docs/escher-integration-plan.md)
delivered first, so a Gutenberg document can carry Escher diagrams as `diagram` blocks. Phases 1 to 3
below do not depend on it; phase 4 does.

---

## 1. Goal

ASI Dewey is a primary tool. After this plan it can **generate diagrams with asi_escher and documents
with asi_gutenberg from its own database**, through the same command path everything else uses:

```powershell
asi-dewey diagram                                   # catalog of diagrams
asi-dewey diagram lifecycle_overview --out out      # out/lifecycle_overview.{png,svg,dot,mmd}
asi-dewey document safety_plan --out out            # out/safety_plan.{md,pdf,docx} with figures
```

and the same two verbs from the window, from a `.jsonl` script, and from an agent calling
`Brain.execute_dict`.

Three principles carry over unchanged from [plan.md](plan.md):

- **The database is the truth; files are views.** A diagram or a document is regenerated on demand,
  exactly like the workbook. Nothing rendered is ever read back into the database.
- **One command path.** The window never calls Escher or Gutenberg directly. It calls
  `Brain.execute("diagram", ...)` and `Brain.execute("document", ...)` with actor `gui`.
- **Registration, not edits.** Diagrams and documents live in catalogs behind factories. A new
  diagram or document is one builder function and one decorator.

Out of scope: storing diagram or document specs in the database, editing diagrams in the window,
reading Markdown back into entities, and anything that would make Dewey import asi_kletz or vice versa.

## 2. What exists today (verified 2026-10-27: the tree before 0.2.0)

| In Dewey | Relevant fact |
|---|---|
| `commands/factory.py` | `@register_command` adds a verb; the CLI parser and `schema` output are generated from `Command.arguments`. |
| `commands/base.py` | `Argument(type="kv")` plus `parse_kv` already give `--filter k=v`; `Result.to_json` uses `default=str`. |
| `commands/dispatcher.py` | Any exception inside `run` becomes `Result.failure`; builders may raise freely. |
| `io/exporters.py` | `ExporterFactory` is the pattern to copy; `_save_with_fallback` handles locked files. |
| `brain.py` | `load_config` reads `db` and `workbook` from `dewey.toml`; `CONFIG_KEYS` is the place to add `out`. |
| `automation/events.py` | `EventBus.publish(topic, **payload)`; the window refreshes on any topic. |
| `storage` | `audit(actor, action, entity, row_id, payload)` records what happened. |
| `gui/screens.py` | `build_default_screens` registers Dashboard, one screen per entity, the matrix (the Safety Plan Matrix screen, removed in 0.4.0), and Export / Import. A new screen is one `register` call. |
| `gui/main_window.py` | `MainWindow.run(verb, **args)` is the only way a screen executes anything; `interactive` guards dialogs in tests. |
| `tests/conftest.py` | Tests are isolated from `dewey.toml` and the environment by an autouse fixture. |

| In the generators | Relevant fact |
|---|---|
| `asi_escher.build(d, out_dir, name, opts, dpi, formats)` | Returns paths per format plus `size`, `nodes`, `edges`, `issues` (a list of `LayoutIssue` objects, not strings). Emits one `LayoutWarning` per diagram with issues. |
| `asi_escher.Diagram` | Shorthand constructors; `lane()` for swimlanes; `to_dict`/`from_dict`; `fill=`/`stroke=` per node. |
| `asi_gutenberg.build(d, out_dir, name, opts, theme)` | Writes the `.md`, parses it back, renders `.pdf` and `.docx` from the parsed Markdown; figure paths resolve against `out_dir`; returns `pages`, stats, `issues` (strings). |
| `asi_gutenberg.Document` | `h1..h4`, `p`, `table`, `fields`, `tasks`, `figure(path, caption)`, `requirement`, `appendix`, `revision`. After the Gutenberg plan: `diagram(spec, caption)`. |
| Palette | Gutenberg's `THEME` already uses the Escher colours, so figures match the text. |

Neither generator is a dependency of Dewey yet. Both are sibling checkouts at `../asi_escher` and
`../asi_gutenberg`.

## 3. Design

### 3.1 Dependencies

```powershell
cd asi_dewey
uv add --editable ../asi_escher
uv add --editable ../asi_gutenberg
```

Both path sources are declared in Dewey's own `pyproject.toml` even though Dewey could reach
Escher through Gutenberg: uv applies `tool.uv.sources` of the root project only, so Gutenberg's
source for Escher is not inherited. Expected result:

```toml
dependencies = ["asi-escher", "asi-gutenberg", "openpyxl>=3.1"]

[tool.uv.sources]
asi-escher = { path = "../asi_escher", editable = true }
asi-gutenberg = { path = "../asi_gutenberg", editable = true }
```

matplotlib, Pillow, reportlab, and python-docx arrive transitively. They are imported **lazily**
inside the builders and commands, the way `openpyxl` is imported inside `ExcelExporter`, so
`asi-dewey list` and window start-up stay as fast as today.

### 3.2 Output folder

A third configurable path, beside `db` and `workbook`:

| Source | Key |
|---|---|
| explicit argument | `--out` on `diagram` and `document` |
| environment | `ASI_DEWEY_OUT` |
| `dewey.toml` | `out = "../some folder/generated"` (relative to the file, like `workbook`) |
| default | `out/` next to the database (`dewey.db` → `out/`), or `./out` for `:memory:` |

`Brain.out_dir` holds the resolved value; `status` reports it as `out_dir`; `CONFIG_KEYS` becomes
`("db", "workbook", "out")`; `dewey.example.toml` documents it. The test fixture clears
`ASI_DEWEY_OUT` like it clears the other two variables.

### 3.3 New package: `asi_dewey/generate/`

```
src/asi_dewey/generate/
  __init__.py       DiagramFactory, DocumentFactory, register_diagram, register_document, Spec
  base.py           Spec (key, title, description, params), Param (name, help, required, default)
  diagrams.py       built-in diagram builders (section 3.4)
  documents.py      built-in document builders (section 3.5)
  figures.py        helpers shared by both: build_diagram(), issues_to_strings(), capture of LayoutWarning
```

A **diagram builder** is `(brain: Brain, params: dict[str, str]) -> asi_escher.Diagram`.
A **document builder** is `(brain: Brain, params: dict[str, str]) -> asi_gutenberg.Document`.
Both are registered with a `Spec`:

```python
from asi_dewey.generate import register_diagram, Spec, Param

@register_diagram(Spec(
    key="lifecycle_overview", title="Safety lifecycle overview",
    description="The ten lifecycle phases in order, each with its deliverable count and status split.",
    params=(),
))
def lifecycle_overview(brain, params):
    from asi_escher import Diagram
    d = Diagram("Safety lifecycle overview", "flowchart", direction="LR")
    ...
    return d
```

The factories mirror `ExporterFactory`: class-level registry, `create(key)`, `keys()`, `specs()`,
`NotFound` with the known keys on a miss. Builders only read through `brain.service(entity).list()`
and `brain.registry`; they never touch storage directly, so an agent-made row and a GUI-made row
look the same to them.

`figures.py` wraps `asi_escher.build` once: it runs it under `warnings.catch_warnings` with
`LayoutWarning` turned into recorded issues, converts each `LayoutIssue` to a plain dict
(`kind`, `message`, `edge`, `node`) so the `Result` serialises cleanly, and returns the paths.
Document builders use the same helper to render the figures they embed.

### 3.4 Diagram catalog (first cut)

| Key | Escher kind | Built from | Params |
|---|---|---|---|
| `schema_map` | `bdd`, frame `bdd [Package] asi_dewey` | One block per registered entity, compartments `fields: n` and `rows: n`, no edges. Works on an empty database; the "is it wired" diagram. | none |
| `lifecycle_overview` | `flowchart`, LR | One `process` node per lifecycle phase (the `lifecycle_phase` lookup, in order), chained; label `"<phase>\n<n> deliverables, <done> done"`. A phase with a Blocked row takes the decision tint (`fill`/`stroke` from `asi_escher.THEME["decision"]`). | none |
| `phase_flow` | `activity` with lanes `Author`, `Verification`, `Reviewer` | For every `safety_plan_row` in one phase, ordered by `order`: an `action` in the Author lane (deliverable, author text, status as stereotype), an `action` in the Verification lane when any `verify_*` flag is set (label = the set flags), an `action` in the Reviewer lane (gate reviewer or set `reviewer_*` flags); `start` → rows → `end`. | `phase` (required): a value of the `lifecycle_phase` lookup, or its leading number (`"3"`) |
| `task_flow` | `flowchart`, TB, lanes = the four `task_class` values | Tasks ordered by `start`, then `order`; one node per task labelled `name` and its dates; chained in that order; done tasks (end date in the past) take the state tint. | `class` (optional): keep one task class only |

Deferred, with the reason: a machine-function-to-use-case map needs a relation entity Dewey does
not have; a Jira state diagram is a bar chart in disguise. Both are one registration away when the
data exists.

### 3.5 Document catalog (first cut)

| Key | Gutenberg kind | Sections | Figures |
|---|---|---|---|
| `safety_plan` | `plan` | Purpose (fixed text); Lifecycle overview (table phase / count / Pending / Ongoing / Blocked / Done); one `h1` per lifecycle phase with two portrait tables, "Deliverables" (Deliverable, Location, Reference, Deadline, Status) and "Ownership" (Deliverable, Author, Verification, Reviewer), the same split Kletz uses; appendix Roles (the author and reviewer flag names); appendix QMS references (`qms_document` rows as Markdown links); appendix Status legend. | `lifecycle_overview`; `phase_flow` for each phase that has rows |
| `status_report` | `report` | Counts (`fields` table from `brain.status()["entities"]`); Open Jira tickets (table, link column); Tasks ending within seven days; Recent changes (last 20 audit entries). | `task_flow`; `lifecycle_overview` |
| `handbook` | `report`, title "Working Knowledge Handbook" | Facts (`fields`); People (table grouped by `person_class`); Links (table, URL as Markdown link); QMS documents; Machine functions; Use cases. | `schema_map` in an appendix |

Document metadata comes from the database where it can: `project` from the fact named `Product`
if present, `date` = today, `author` = the actor that ran the command, `status` = Draft. Missing
facts leave the field blank; they never fail the build. The output stem is the catalog key, so a
rebuild overwrites.

Dewey's `safety_plan` carries **no document id**. The controlled Safety Plan is Kletz's: its id
lives in `kletz.toml` and its reviewed form is the PDF Kletz produces (decided 2026-10-27). Dewey's
version is a working view of the same matrix for the engineer's own use, and its subtitle says so
("working copy, not the controlled document"). Like Kletz, the `document` result carries
`"primary"`, the PDF, and the Generate screen's **Open file** opens it.

Until the Gutenberg plan lands, document builders render figures with `figures.py` into
`<out>/figures/` and add them with `doc.figure("figures/<key>.png", caption)`. After it lands, they
call `doc.diagram(diagram_builder(brain, params), caption)` and let Gutenberg render; the
`figures.py` path stays for the `diagram` verb.

### 3.6 Commands

`commands/generate.py`, registered like the others:

```
diagram  [name] [--out <dir>] [--formats png,svg,dot,mmd] [--param k=v ...] [--dpi 160]
document [name] [--out <dir>] [--param k=v ...]
```

- No `name`: `Result.success({"catalog": [spec.to_dict() ...]})`. Agents discover the catalog
  the way they discover entities with `schema`.
- With `name`: build into `--out` or `brain.out_dir`.
- `diagram` data: `{"name", "title", "paths": {png, svg, dot, mmd}, "size", "nodes", "edges", "issues"}`;
  every issue message is also a `Result.warning`, so a degraded layout is visible on the CLI and in
  the window log without failing the command.
- `document` data: `{"name", "title", "paths": {md, pdf, docx}, "pages", "figures": [...], "stats", "issues"}`;
  Gutenberg issues (dangling traces, missing figure files) become warnings.
- Unknown name, unknown param, missing required param: `Result.failure` with the known keys or
  params listed, produced by the factory and `Spec.check_params`, never by a traceback.
- Locked output file (a PDF open in a viewer): Gutenberg raises `PermissionError`; the command
  retries with a timestamped stem using the same rule as `_save_with_fallback` and reports it in
  `warnings`.
- Both verbs `audit(actor, "generate", name, None, {"kind": ..., "paths": ...})` and
  `events.publish("generated", kind="diagram"|"document", name=..., paths=..., actor=...)`, so the
  dashboard's recent-changes list and the open screen see it.

`status` lists the new verbs automatically through `factory.verbs()`.

### 3.7 Window

A new screen, key `generate`, title **Generate**, registered in `build_default_screens` after
Export / Import. Layout, top to bottom:

1. Output folder entry with Browse (defaults to `brain.out_dir`).
2. Two list boxes side by side: Diagrams and Documents, filled from the two catalogs, with the
   spec description shown under the selection.
3. A small parameter form generated from `Spec.params` of the selected item (an `Entry` per
   param; a lookup `Combobox` when a param names a lookup, as `phase` does).
4. Buttons: **Build**, **Open file** (the PNG or the PDF through `os.startfile`), **Open folder**.
5. A result log like the Export / Import screen's, fed from the `Result`.

The screen calls `self.window.run("diagram", ...)` or `self.window.run("document", ...)` and
nothing else. The File menu gets **Build document…** (shows the Generate screen with the
Documents list focused). No new accelerator; Ctrl+E stays the workbook.

Rendering a long document takes seconds. First cut: synchronous with `set_status("Building …")`
and the cursor set to `watch`. If it bothers, run it in a thread and marshal the `Result` back with
`after`, the way `_refresh_after_event` already schedules work.

### 3.8 Scripts and agents

A `.jsonl` step is the wire form of the verb:

```jsonl
{"verb": "document", "args": {"name": "safety_plan", "out": "out"}, "actor": "claude"}
{"verb": "diagram", "args": {"name": "phase_flow", "param": {"phase": "3"}}}
```

`--param` accepts `k=v` strings on the CLI and a JSON object from scripts and `execute_dict`,
exactly as `--filter` does today through `parse_kv`.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Wiring | Dependencies added and locked; `out` config, env, and `Brain.out_dir`; `generate/` package with both factories and `figures.py`; `schema_map` diagram; `diagram` verb incl. catalog listing. | `asi-dewey diagram schema_map` writes four files from an empty database; tests in section 6 for phase 1 pass. |
| 2. Diagrams | `lifecycle_overview`, `phase_flow`, `task_flow`. | Each renders from the seeded test database without layout issues; `--param` validation errors are `Result.failure`. |
| 3. Documents | `document` verb; `safety_plan`, `status_report`, `handbook` using `doc.figure` on files from `figures.py`. | Triplets written; the Markdown references existing PNGs; page count > 1 for `safety_plan`. |
| 4. Gutenberg diagram blocks | Switch document builders to `doc.diagram(...)` once asi_gutenberg 0.2.0 exists; drop the pre-render step from the document path. | No `figure placeholder` in any generated PDF; `figures/` is produced by Gutenberg. |
| 5. Window | Generate screen, File menu entry, GUI tests. | Screen builds and runs both verbs with the window withdrawn. |
| 6. Release | README section "Diagrams and documents", CHANGELOG `0.2.0`, `version.py`, `dewey.example.toml`, pointer from `plan.md` section 10, tag `v0.2.0`. | `uv run pytest` and `uv run ruff check src tests` clean. |

Phases 1 to 3 and 5 do not wait for the Gutenberg plan. Phase 4 does.

## 5. Files touched

```
pyproject.toml                       dependencies, tool.uv.sources, version
uv.lock                              regenerated
dewey.example.toml                   out = "..."
src/asi_dewey/version.py             0.2.0
src/asi_dewey/brain.py               ENV_OUT, CONFIG_KEYS, out_dir, status()
src/asi_dewey/generate/              new package (section 3.3)
src/asi_dewey/commands/generate.py   diagram, document verbs
src/asi_dewey/commands/__init__.py   import generate (registers the verbs)
src/asi_dewey/gui/generate_screen.py new screen
src/asi_dewey/gui/screens.py         register "generate"
src/asi_dewey/gui/main_window.py     File > Build document…
tests/test_generate.py               new
tests/test_gui.py                    Generate screen cases
tests/conftest.py                    clear ASI_DEWEY_OUT
README.md, CHANGELOG.md, docs/plan.md
```

Nothing in `schema/`, `storage/`, `repositories/`, or `services/` changes. No migration: the
schema version stays 1.

## 6. Tests

Real generators, no mocks; they are deterministic and fast enough (the Escher suite renders sixteen
diagrams in a few seconds).

- Catalog: `diagram` and `document` without a name list every registered key with title,
  description, and params; `status()["commands"]` contains both verbs.
- `schema_map` on an empty `Brain` writes `png`, `svg`, `dot`, `mmd`; `data["nodes"]` equals the
  number of registered entities.
- `lifecycle_overview` and `task_flow` on the `seeded` fixture: files exist, `issues == []`.
- `phase_flow` without `phase`: failure naming the param; with `phase="1"` and with the full phase
  label: same output.
- Unknown name: failure listing the known keys.
- `document safety_plan` on `seeded`: three files, `pages >= 2`, the Markdown contains
  `![Figure 1:` and the referenced PNG exists under `out`; `issues == []`.
- `handbook` on an empty database builds (empty tables, no crash).
- Locked PDF: monkeypatch `render_pdf` to raise `PermissionError` once; the result path carries a
  timestamp and a warning.
- Audit and events: after a build, `audit_tail(1)` has action `generate` and `events.last(1)` has
  topic `generated`.
- Out-dir precedence: argument beats `ASI_DEWEY_OUT` beats `dewey.toml` beats the default next to
  the database (same shape as the existing workbook-precedence tests).
- CLI: `asi-dewey diagram schema_map --out <tmp>` exits 0 and prints a JSON `Result`.
- GUI (skipped without a display): the Generate screen appears in `factory.items()`; selecting a
  diagram and pressing Build logs `[ok] diagram`; the Open buttons are disabled until a build
  succeeds.

## 7. Risks and decisions

| Risk | Decision |
|---|---|
| Transitive path source not inherited by uv | Declare both sources in Dewey (section 3.1). |
| Start-up cost of matplotlib and reportlab | Lazy imports inside builders and commands; a test asserts that importing `asi_dewey` does not import `matplotlib`. |
| `LayoutIssue` objects in `Result.data` | Converted to dicts in `figures.py`; `to_json` never sees them. |
| Escher's `LayoutWarning` surfacing as a Python warning in the CLI | Caught in `figures.py` and turned into warnings on the `Result`; tests keep `-W error` for it inside the generator repos only. |
| `os.startfile` is Windows-only | Guarded; on other platforms the Open buttons fall back to printing the path in the log. |
| Long `phase_flow` labels (23 reference flags, 17 author roles) | Builders label nodes with the set flags only, and truncate to the first three plus `+n`. |
| Document builders duplicating dashboard logic | The dashboard's queries (open Jira, tasks ending this week, recent audit) move to small functions in `services/` that both the screen and `status_report` call. |
| Demo figure names in Gutenberg use the Escher example names | Irrelevant to Dewey: its figures are generated, never copied. |

## 8. Open questions

None. Decided 2026-10-27:

- **No `document --spec file.json` in 0.2.0.** Every document an agent can produce goes through the
  catalog, so its content is reviewable code with tests, not an ad-hoc spec. An agent that needs a
  one-off document calls `asi_gutenberg` directly in Python. Revisit if a real need appears.
- **No throttling.** The window and an agent share one `Brain`; builds are synchronous and the
  last writer wins, as with the workbook. Revisit with the automation server.
- Per-phase tables are split like Kletz's (section 3.5) so the PDF stays portrait.

## 9. Change log

- 2026-10-27 Draft 0.3: remaining questions decided: no spec-file verb and no throttling in
  0.2.0; per-phase tables split into "Deliverables" and "Ownership". No open questions remain.
- 2026-10-27 Draft 0.2: the Safety Plan document id belongs to Kletz (`kletz.toml`), so Dewey's
  `safety_plan` carries none and is labelled a working copy; the PDF is the primary output of
  every document (`primary` in results, **Open file** shows it). Open question removed.
- 2026-10-27 Draft 0.1: goal, verified starting point, dependencies, output folder, `generate/`
  package, diagram and document catalogs, verbs, window, phases, files, tests, risks, open questions.
