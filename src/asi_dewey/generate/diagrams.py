"""Built-in diagram catalog.

Each builder reads the database through ``brain.service(entity)`` and the registry, and
returns an ``asi_escher.Diagram``. ``asi_escher`` is imported inside the builder so that
``import asi_dewey`` (and the window's start-up) never loads matplotlib.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from ..schema import FieldSpec, slugify
from .base import Param, Spec
from .factory import register_diagram

if TYPE_CHECKING:
    from ..brain import Brain

MAX_LISTED = 3  # flags shown on a node before "+n"
PLAN = "safety_plan_row"


# -- helpers ----------------------------------------------------------------
def set_flags(row: dict[str, Any], specs: list[FieldSpec]) -> list[str]:
    """Headers of the boolean columns that are set on ``row``."""
    return [spec.header for spec in specs if row.get(spec.name)]


def short_list(items: list[str], limit: int = MAX_LISTED) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" +{len(items) - limit}" if len(items) > limit else "")


def one_line(text: Any) -> str:
    return " ".join(str(text or "").split())


def flag_specs(brain: Brain, group: str) -> list[FieldSpec]:
    return [s for s in brain.registry.get(PLAN).groups().get(group, []) if s.is_flag]


def resolve_phase(brain: Brain, value: Any) -> str:
    """A lifecycle phase from its lookup value, its leading number (``"3"``), or a case-insensitive match."""
    phases = brain.lookups.get("lifecycle_phase", ())
    text = one_line(value)
    if text in phases:
        return text
    for phase in phases:
        number = phase.split(".", 1)[0].strip()
        if text.rstrip(".") == number or text.casefold() == phase.casefold():
            return phase
    raise CommandError(f"unknown lifecycle phase {value!r}; known: {', '.join(phases)}")


def plan_rows(brain: Brain, phase: str | None = None) -> list[dict[str, Any]]:
    filters = {"lifecycle_phase": phase} if phase else None
    return brain.service(PLAN).list(filters, order_by="order,id")


# -- schema_map ---------------------------------------------------------------
@register_diagram(Spec(
    key="schema_map", title="Schema map",
    description="One block per registered entity with its field and row counts; the 'is it wired' diagram, "
                "works on an empty database.",
))
def schema_map(brain: Brain, params: dict[str, str]) -> Any:
    from asi_escher import Diagram

    d = Diagram("Schema map", "bdd", direction="TB", frame="bdd [Package] asi_dewey")
    for schema in brain.registry:
        d.node(
            schema.name, schema.label, "block", stereotype="entity",
            compartments=[
                ("", [f"fields: {len(schema.visible_fields)}", f"rows: {brain.service(schema.name).count()}"]),
            ],
        )
    return d


# -- lifecycle_overview -------------------------------------------------------
@register_diagram(Spec(
    key="lifecycle_overview", title="Safety lifecycle overview",
    description="The lifecycle phases in order, each with its deliverable count and how many are done; "
                "a phase with a blocked deliverable takes the decision tint.",
))
def lifecycle_overview(brain: Brain, params: dict[str, str]) -> Any:
    from asi_escher import THEME, Diagram

    d = Diagram("Safety lifecycle overview", "flowchart", direction="LR")
    rows = plan_rows(brain)
    ids: list[str] = []
    for index, phase in enumerate(brain.lookups.get("lifecycle_phase", ()), start=1):
        mine = [r for r in rows if r.get("lifecycle_phase") == phase]
        done = sum(1 for r in mine if r.get("status") == "Done")
        blocked = any(r.get("status") == "Blocked" for r in mine)
        fill, stroke = THEME["decision"] if blocked else (None, None)
        node_id = f"phase_{index}"
        d.node(node_id, f"{phase}\n{len(mine)} deliverables, {done} done", "process", fill=fill, stroke=stroke)
        ids.append(node_id)
    d.chain(*ids)
    return d


# -- phase_flow ---------------------------------------------------------------
@register_diagram(Spec(
    key="phase_flow", title="Phase flow",
    description="The deliverables of one lifecycle phase, in order, as an activity diagram with Author, "
                "Verification and Reviewer lanes.",
    params=(Param("phase", "Lifecycle phase: its lookup value or its leading number, e.g. 3",
                  required=True, lookup="lifecycle_phase"),),
))
def phase_flow(brain: Brain, params: dict[str, str]) -> Any:
    from asi_escher import Diagram

    phase = resolve_phase(brain, params["phase"])
    author_flags = flag_specs(brain, "author")
    verify_flags = flag_specs(brain, "verification")
    reviewer_flags = flag_specs(brain, "reviewer")

    d = Diagram(f"Phase flow: {phase}", "activity", direction="TB")
    d.lane("author", "Author")
    d.lane("verification", "Verification")
    d.lane("reviewer", "Reviewer")
    d.start(lane="author")
    previous = "start"
    for row in plan_rows(brain, phase):
        deliverable = one_line(row.get("deliverable")) or f"deliverable {row['id']}"
        label = deliverable
        if row.get("status"):
            label += f"\nÂ«{one_line(row['status'])}Â»"
        authors = ([one_line(row["author"])] if row.get("author") else []) + set_flags(row, author_flags)
        if authors:
            label += "\n" + short_list(authors)
        node_id = f"row{row['id']}_author"
        d.action(node_id, label, lane="author")
        d.edge(previous, node_id)
        previous = node_id

        verification = set_flags(row, verify_flags)
        if verification:
            node_id = f"row{row['id']}_verify"
            d.action(node_id, short_list(verification), lane="verification")
            d.edge(previous, node_id)
            previous = node_id

        gate = [one_line(row["gate_reviewer"])] if row.get("gate_reviewer") else []
        reviewers = gate + set_flags(row, reviewer_flags)
        if reviewers:
            node_id = f"row{row['id']}_review"
            d.action(node_id, short_list(reviewers), lane="reviewer")
            d.edge(previous, node_id)
            previous = node_id
    d.end(lane="author")
    d.edge(previous, "end")
    return d


# -- task_flow ----------------------------------------------------------------
@register_diagram(Spec(
    key="task_flow", title="Task flow",
    description="Every task in start-date order, one lane per task class, chained; a task whose end date "
                "has passed takes the state tint.",
    params=(Param("class", "Keep one task class only", lookup="task_class"),),
))
def task_flow(brain: Brain, params: dict[str, str]) -> Any:
    from asi_escher import THEME, Diagram

    classes = list(brain.lookups.get("task_class", ()))
    wanted = params.get("class")
    if wanted and wanted not in classes:
        raise CommandError(f"unknown task class {wanted!r}; known: {', '.join(classes)}")
    tasks = brain.service("task").list({"task_class": wanted} if wanted else None, order_by="start,order,id")

    lanes = [wanted] if wanted else classes
    for task in tasks:
        name = task.get("task_class") or "unclassified"
        if name not in lanes:
            lanes.append(name)
    d = Diagram("Task flow" + (f": {wanted}" if wanted else ""), "flowchart", direction="TB")
    for name in lanes:
        d.lane(f"lane_{slugify(name)}", name)
    if not tasks:
        d.note("empty", "No tasks recorded", lane=f"lane_{slugify(lanes[0])}")
        return d

    today = dt.date.today()
    done_fill, done_stroke = THEME["state"]
    previous: str | None = None
    for task in tasks:
        lane = f"lane_{slugify(task.get('task_class') or 'unclassified')}"
        dates = " â†’ ".join(x for x in (task.get("start"), task.get("end")) if x)
        label = one_line(task.get("name")) + (f"\n{dates}" if dates else "")
        done = bool(task.get("end")) and dt.date.fromisoformat(task["end"]) < today
        node_id = f"task_{task['id']}"
        fill, stroke = (done_fill, done_stroke) if done else (None, None)
        d.node(node_id, label, "process", lane=lane, fill=fill, stroke=stroke)
        if previous:
            d.edge(previous, node_id)
        previous = node_id
    return d


# -- stpa_trace ---------------------------------------------------------------
TRACE_LABEL_CHARS = 48
RETIRED_TINT = "state"


def short(text: Any, limit: int = TRACE_LABEL_CHARS) -> str:
    line = one_line(text)
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


@register_diagram(Spec(
    key="stpa_trace", title="STPA trace",
    description="Hazards, unsafe control actions, loss scenarios and constraints of one analysis as four columns "
                "with the edges the page states; a swimlane per controller of the linked control structure when "
                "the UCAs are linked to one, a retired UCA in the state tint, a duplicate as a dashed edge.",
    params=(Param("analysis", "The analysis: its id, uid or slug", required=True),),
))
def stpa_trace(brain: Brain, params: dict[str, str]) -> Any:
    from asi_escher import THEME, Diagram

    row = brain.stpa.resolve(params["analysis"])
    parts = brain.stpa.parts(row["slug"])
    hazards = {h["code"]: h for h in parts["hazards"]}
    ucas = {u["code"]: u for u in parts["ucas"]}
    constraints = {c["code"]: c for c in parts["constraints"]}
    linked = [u["cs_controller"] for u in parts["ucas"] if u.get("cs_controller")]
    structure = row.get("control_structure")
    lanes: dict[str, str] = {}  # lane id -> title, in order; empty: a plain layered graph, left to right
    if structure and linked:
        order = {c["key"]: (c.get("order") or 0, c.get("name") or c["key"])
                 for c in brain.service("cs_controller").list({"structure": structure})}
        lanes["lane_hazards"] = "Hazards"
        for key in sorted(dict.fromkeys(linked), key=lambda k: order.get(k, (10**6, k))):
            lanes[f"lane_{slugify(key)}"] = order.get(key, (0, key))[1]
        if any(not u.get("cs_controller") for u in parts["ucas"]):
            lanes["lane_unlinked"] = "Not linked"
        lanes["lane_constraints"] = "Constraints"
    d = Diagram(f"STPA trace: {row['name']}", "flowchart", direction="TB" if lanes else "LR")
    for lane_id, title in lanes.items():
        d.lane(lane_id, title)

    def lane_of(uca: dict[str, Any] | None) -> str | None:
        if not lanes:
            return None
        if uca is None or not uca.get("cs_controller"):
            return "lane_unlinked"
        return f"lane_{slugify(uca['cs_controller'])}"

    retired_fill, retired_stroke = THEME[RETIRED_TINT]
    for code, h in hazards.items():
        d.node(f"h_{slugify(code)}", f"{code}\n{short(h.get('text'))}", "io", lane="lane_hazards" if lanes else None)
    for code, u in ucas.items():
        label = f"{code}\n{short(u.get('text'))}"
        if u.get("retired"):
            label += "\n«retired»"
        tint = (retired_fill, retired_stroke) if u.get("retired") else (None, None)
        d.node(f"u_{slugify(code)}", label, "process", lane=lane_of(u), fill=tint[0], stroke=tint[1])
    for code, c in constraints.items():
        d.node(f"c_{slugify(code)}", f"{code}\n{short(c.get('text')) or '(referenced only)'}", "document",
               lane="lane_constraints" if lanes else None)
    for s in parts["scenarios"]:
        uca = ucas.get(s.get("uca") or "")
        row_text = f"row {s['row']}" if s.get("row") is not None else f"order {s.get('order')}"
        head = s.get("counterpart") or s.get("uca") or row_text
        if s.get("row") is not None:
            head += f" ({row_text})"
        types = ", ".join(f"type {t}" for t in s.get("types") or [])
        label = "\n".join(x for x in (head, types, short(s.get("causal_factors"))) if x)
        node_id = f"s_{s['id']}"
        d.node(node_id, label, "action", lane=lane_of(uca))
        if uca is not None:
            d.edge(f"u_{slugify(uca['code'])}", node_id)
        for c in s.get("constraints") or []:
            if c in constraints:
                d.edge(node_id, f"c_{slugify(c)}")
    for code, u in ucas.items():
        for h in u.get("hazards") or []:
            if h in hazards:
                d.edge(f"h_{slugify(h)}", f"u_{slugify(code)}")
        if u.get("duplicate_of") in ucas:
            d.edge(f"u_{slugify(code)}", f"u_{slugify(u['duplicate_of'])}", "duplicate of", style="dashed")
    if not d.nodes:
        d.note("empty", "The analysis holds no objects yet", lane="lane_hazards" if lanes else None)
    return d
