# Control structures: a CRUD screen, a factory, and four ways out

Status: **Planned** (written 2026-10-29). Owner's ask of 2026-10-29: "introduce a screen that is used as a
CRUD for STPA control structures; the idea is that we would be able to use the factory design pattern to
build a control structure, or many; we need to make control structures like the one in Roy's Brain, feel
free to use the schema; users make control architectures that we will use for STPA later, and the user can
export them to their folder of preference, selecting the format: png pydraw and/or svg pydraw and/or png
drawio and/or svg drawio, or drawio drawio, where pydraw automatically makes svg and png and drawio makes
drawings by getting the positioning from the automatically positioned pydraw; the user can pick which of
the formats they want; there must be Select all / Select none buttons; the default must be drawio png."

## 1. What exists, and what the plan builds on

- **The model to copy** is the wheel loader master control structure in Roy's Brain (`control structures/`):
  a draw.io file (`source/WL_Control_Structure.drawio`), a script (`control_structure_to_datasets.py`) that
  parses it into six datasets, and the datasets themselves: 8 controllers (kind: controller / controlled
  process / environment; a responsibility; a process-model title), 30 algorithms (M1, S3, V1 ... each owned
  by a controller), 18 process-model entries (a heading naming control actions, the variables the decision
  depends on, which feedback updates them), 58 signals (CA-xx control actions, FB-xx feedback, each with a
  name, a source and a target), 21 edges (an arrow carrying signals), 1 note. That is the schema: the plan
  adopts it as is, with the ids the datasets already use.
- **asi_escher** ("pydraw" in the owner's words) lays out and renders diagrams deterministically to PNG and
  SVG and exports DOT and Mermaid. It has no control-structure kind and no draw.io writer yet. Its layout
  produces every node's x, y, width, height and every edge's routed points: exactly what a draw.io file needs.
- **asi_dewey** is the working-knowledge API with the schema-driven entities, the CLI, the window and the
  Escher/Gutenberg views; STPA knowledge belongs here. Kletz plans the deliverables and stays out of it.
- **draw.io desktop is not installed on the owner's machine today.** The drawio PNG and SVG formats are
  draw.io's own exports (`draw.io.exe --export`); without the program they cannot be made. See section 7.
- **The compactor STPA and the wheel loader structure are ASI-internal.** asi_dewey and asi_escher are
  public repositories: the real structure never enters them. Tests and demos use a synthetic structure
  with neutral names; the real one lives in the owner's database, imported from his draw.io file, and may
  be kept as a dataset in asi_standards (private) if he wants it versioned.

## 2. The entities (asi_dewey, schema version +1)

One control structure holds everything; every child row names its structure, so many structures coexist
("or many"). Ids are stable slugs so the later STPA steps (unsafe control actions, loss scenarios) can point
at a signal by `CA-13` and a controller by `vak_controller` across exports.

| Entity | Fields (beyond id, uid, created/updated) | From the dataset |
|---|---|---|
| `control_structure` | name, slug, system (e.g. "ASI autonomous wheel loader"), description, source (file or "built by hand"), status (Draft / Reviewed / Baselined), revision | the folder |
| `cs_controller` | structure, order, name, kind (controller, controlled_process, environment, human_controller, sensor, actuator), responsibility (multiline), process_model_title, note | `controllers.json` |
| `cs_algorithm` | controller, order, code (V1), name | `algorithms.json` |
| `cs_process_model_entry` | controller, order, heading, control_actions (list of signal ids), variables (list), updated_by (list of signal ids), references | `process_model_entries.json` |
| `cs_edge` | structure, order, kind (control_action, feedback), source (controller), target (controller) | `edges.json` |
| `cs_signal` | edge, order, signal_id (CA-xx / FB-xx), kind, name, placeholder (bool) | `signals.json` |
| `cs_note` | structure, text, attached_to (controller or empty) | `notes.json` |

Rules the service enforces: a signal's kind matches its edge's kind; a control action points down the
hierarchy and feedback up (a warning, not a refusal: the owner's structure has lateral stop paths); signal
ids are unique within a structure; deleting a controller deletes its algorithms, process-model entries and
the edges touching it (asked once in the window, `--cascade` on the CLI); duplicating a structure deep-copies
everything under a new slug. Lists (`control_actions`, `variables`, `updated_by`) are JSON arrays in text
columns, as the people lists of Kletz 0.19.0 are, edited one per line.

## 3. The factory

`asi_dewey/stpa/factory.py`: `ControlStructureFactory` with a registry of named **builders**, each a
callable `(brain, **options) -> control_structure id`, so a structure can be made several ways and the
window offers them as "New from":

- `blank(name, system)`: the structure and nothing else.
- `template:wheel_loader_master`: the owner's eight boxes, their algorithms, process models and the 21
  arrows, generated from a dataset file the owner points the configuration at (`control_structures_dir`
  in dewey.toml, default `../asi_standards/control-structures/`, private); absent, the builder is listed
  as unavailable. The compactor-derived numbering is kept as it is in the datasets.
- `from_drawio(path)`: the parser of `control_structure_to_datasets.py` ported into Dewey
  (`stpa/drawio_reader.py`, standard library only, as the script is), producing the same six datasets and
  loading them. Round trip: a structure exported as `.drawio` imports back to the same rows.
- `from_datasets(folder)`: the six JSON files as the script writes them (the Roy's Brain envelope).
- `clone(existing, name)`: duplicate.

The factory also builds the *drawing*: `to_diagram(structure) -> asi_escher.Diagram` with the new
control-structure kind (section 4), the single place that decides how a controller becomes a box and an
edge an arrow. Every export and the window's preview go through it, so they can never disagree.

## 4. asi_escher: the control-structure kind and the draw.io writer (asi_escher 0.2.0)

- **Diagram kind `control_structure`**: a node is a box with three stacked sections (responsibility; the
  algorithms, orange; the process model, blue), `kind` driving the box style (a double border for the
  controlled process, a dashed one for the environment, a rounded one for a human controller). An edge is
  `control_action` (red, arrowhead down) or `feedback` (blue, arrowhead up), its label the signal lines
  (`CA-01 Mission Data`). Layout: top-down by hierarchy (operators, supervisor, vehicle controller,
  machine, environment), control actions preferring the left of a pair of boxes and feedback the right, so
  the two arrows between two boxes do not overlap; the existing layered engine does the rest.
- **`to_drawio(diagram) -> str`** in `export.py`: mxGraph XML with one `mxCell` vertex per box
  (`mxGeometry` x, y, width, height straight from the layout; the sections as an HTML label, or as child
  cells when draw.io's container style is used), one edge cell per arrow with the routed points as
  `mxPoint` waypoints, styles that match the renderer's colours. draw.io opens it with every box where
  escher put it: "drawio makes drawings by getting the positioning from the automatically positioned
  pydraw". The file is also the editable master a person can refine in draw.io by hand.
- **`render_with_drawio(drawio_path, fmt, out_path)`**: draw.io desktop's export (`draw.io.exe --export
  --format png|svg --output <file> <drawio>`, scale 2 for PNG), located from `drawio_exe` in the
  configuration, else `%LOCALAPPDATA%\Programs\draw.io\draw.io.exe`, else `C:\Program Files\draw.io\`,
  else `drawio` on PATH. The process it starts is ended afterwards, as Gutenberg does with Word. Absent, a
  clear refusal naming the installer, never a silent substitute (the owner asked for draw.io's picture).
- **Formats** as one enumeration shared by escher, Dewey and the window:

  | Key | Produces | Made by |
  |---|---|---|
  | `pydraw-png` | `<slug>.pydraw.png` | escher's renderer |
  | `pydraw-svg` | `<slug>.pydraw.svg` | escher's renderer |
  | `drawio-png` | `<slug>.drawio.png` (and `<slug>.drawio`) | draw.io desktop from the written file |
  | `drawio-svg` | `<slug>.drawio.svg` (and `<slug>.drawio`) | draw.io desktop from the written file |
  | `drawio` | `<slug>.drawio` | escher's writer |

  Any drawio format writes the `.drawio` file first; selecting `drawio` alone writes only that. The
  default selection is `drawio-png`. `asi-escher export <spec.json> --format drawio-png --format pydraw-svg --out <dir>` on the command line.

## 5. The screen (asi_dewey window)

A new navigation entry **Control structures** (`gui/control_structure_screen.py`), the family's own
conventions (one database, verbs behind every button, nothing on the UI thread but the verb call, the
wheel rule of Kletz 0.15.2, unique Treeview iids):

- **Left**: the structures, one row each (name, system, status, revision, counts), with New from…
  (the factory's builders), Duplicate, Delete, Import draw.io…, Export….
- **Middle**: the selected structure's parts as a stacked tree, the same `stack()` idea as the Safety
  Plan: a controller row, under it its algorithms, its process-model entries, and the arrows that leave it
  with their signals; a search box; a form below the tree for whatever row is selected (controller /
  algorithm / process-model entry / edge / signal / note), with Save, New child, Delete. Lists are edited
  one item per line.
- **Right**: the preview, escher's PNG of the structure re-rendered after every save (off the UI thread,
  the file in the out folder's `figures/`), with a "Open in draw.io" button when draw.io is installed.
- **Export… dialog**: the destination folder (remembered in the preferences, the last one used), the five
  format check boxes with **Select all** and **Select none**, `drawio-png` checked by default, a Preview of
  the file names, Export. Formats draw.io cannot make are shown disabled with the reason when it is not
  installed. The result names every file written in the status bar and in the Result an agent reads.
- The automation server exposes the screen (`/screen {"show": "control_structures"}`) and the verbs, so an
  agent can build or export a structure the way it drives everything else.

## 6. The verbs (asi_dewey CLI, `cs`)

`cs list | get <id> | new <builder> [--name --system --from <file>] | duplicate <id> --name | delete <id>
[--cascade] | validate <id> | import <drawio-or-folder> | export <id> --out <dir> [--format <key>]...
[--all]`, plus the generic `create/update/delete` on the seven entities for the parts. Every verb a JSON
Result, audited, an event per change (`cs.changed`, `cs.exported`), as the rest of Dewey.

## 7. Decisions for the owner

1. **Install draw.io desktop** (the free app; its command line is what makes `drawio-png`, the default).
   Until it is installed the default format cannot be produced and the dialog says so; the other three
   work. If installing it is not possible on the corporate machine, the fallback would be escher rendering
   the PNG from the same positions and naming it `drawio-png` anyway, which the plan does not do without
   his say-so.
2. **Where the real wheel loader structure lives**: his database only (imported once from the Brain's
   draw.io file), or also as datasets under asi_standards (private) so it is versioned with the other
   controlled material. The public repositories never hold it either way.
3. **Numbering**: keep the compactor-inherited CA/FB numbers (gaps included) or renumber when the structure
   is baselined. The plan keeps them.

## 8. Phases and versions

| Phase | Repo | Content | Tests |
|---|---|---|---|
| 1 | asi_escher 0.2.0 | the `control_structure` kind, layout rules, `to_drawio`, `render_with_drawio`, the format set, CLI `export --format` | a synthetic eight-box structure rendered PNG/SVG, its draw.io XML parsed back (positions equal the layout), the draw.io detection and refusal, the gallery example |
| 2 | asi_dewey 0.9.0 | the seven entities (schema +1, migration), the service rules, the factory and its builders, `from_drawio` reader, `cs` verbs, export through escher | round trip draw.io → rows → draw.io, cascade delete, duplicate, validation, every verb, a synthetic template dataset |
| 3 | asi_dewey 0.10.0 | the screen, the export dialog, the preview, the automation surface, README, charter | the window tests of the family: stack, form, dialog defaults (drawio-png), Select all / none, export result |
| 4 | later | STPA step 1 and 2 on top: unsafe control actions per signal, loss scenarios, the Kletz deliverables "STPA step 1/2" pointing at a baselined structure | — |

Each phase is one release with its changelog entry and the owner's words; nothing is pushed or tagged
without him. Estimated effort: phase 1 one working day, phase 2 one, phase 3 one and a half.
