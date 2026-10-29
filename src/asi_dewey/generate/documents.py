"""Built-in document catalog.

Each builder reads the database through ``brain.service(entity)`` and returns an
``asi_gutenberg.Document``. Figures are catalog diagrams added with ``add_figure``; the
``document`` verb renders them into ``<out>/figures/`` before the triplet is written.
``asi_gutenberg`` is imported inside the builders so ``import asi_dewey`` stays light.

Document metadata comes from the database where it can: ``project`` from the fact named
``Product`` when present, ``date`` today, ``status`` Draft. The author is the actor that ran
the command; the verb fills it in. No person is named here.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from ..schema import FieldSpec
from .base import Param, Spec
from .diagrams import PLAN, one_line, set_flags
from .factory import register_document
from .figures import add_figure

if TYPE_CHECKING:
    from ..brain import Brain

PRODUCT_FACT = "Product"
STATUS_MEANING = {
    "Pending": "Not started; the phase has not reached this deliverable.",
    "Ongoing": "Work has started and the deliverable is not yet complete.",
    "Blocked": "Work cannot continue until a named impediment is removed.",
    "Alternative": "The deliverable is covered by another work product.",
    "Out-of-Scope": "Not required for this programme; the reason is recorded on the row.",
    "Done": "Complete, verified, and reviewed as the matrix requires.",
}
SAFETY_PLAN_PURPOSE = (
    "This document is a working view of the platform safety plan matrix kept in the working-knowledge "
    "database. It lists, per safety lifecycle phase, every deliverable with where it lives, which QMS "
    "documents it references, who authors, verifies, and reviews it, its deadline, and its status. "
    "It is regenerated from the database on demand and is **not** the controlled Safety Plan."
)


# -- helpers ----------------------------------------------------------------
def product(brain: Brain) -> str:
    for fact in brain.service("fact").list():
        if one_line(fact.get("name")).casefold() == PRODUCT_FACT.casefold():
            return one_line(fact.get("text"))
    return ""


def new_document(brain: Brain, title: str, kind: str, **kw: Any) -> Any:
    from asi_gutenberg import Document

    return Document(title, kind, date=dt.date.today().isoformat(), status="Draft", project=product(brain), **kw)


def md_link(name: Any, url: Any) -> str:
    name, url = one_line(name), one_line(url)
    return f"[{name}]({url})" if url and name else (url or name)


def joined(*parts: str) -> str:
    return "; ".join(p for p in parts if p)


def flags_text(row: dict[str, Any], specs: list[FieldSpec]) -> str:
    return ", ".join(set_flags(row, specs))


def groups_of(brain: Brain, entity: str) -> dict[str, list[FieldSpec]]:
    groups = brain.registry.get(entity).groups()
    return {name: [s for s in specs if s.is_flag] for name, specs in groups.items() if name}


def table_or_note(doc: Any, columns: list[str], rows: list[list[Any]], caption: str, empty: str) -> None:
    if rows:
        doc.table(columns, rows, caption)
    else:
        doc.p(empty)


# -- safety_plan --------------------------------------------------------------
@register_document(Spec(
    key="safety_plan", title="Safety plan (working copy)",
    description="The safety plan matrix as a plan document: lifecycle overview, one section per phase with "
                "deliverables and ownership tables and a phase flow diagram, and appendices for roles, QMS "
                "references and the status legend. A working view, not the controlled Safety Plan.",
))
def safety_plan(brain: Brain, params: dict[str, str]) -> Any:
    doc = new_document(brain, "Safety Plan", "plan", subtitle="Working copy, not the controlled document")
    groups = groups_of(brain, PLAN)
    rows = brain.service(PLAN).list(order_by="order,id")
    phases = list(brain.lookups.get("lifecycle_phase", ()))
    statuses = list(brain.lookups.get("plan_status", ()))

    doc.h1("Purpose")
    doc.p(SAFETY_PLAN_PURPOSE)

    doc.h1("Lifecycle overview")
    counted = ["Pending", "Ongoing", "Blocked", "Done"]
    overview = []
    for phase in phases:
        mine = [r for r in rows if r.get("lifecycle_phase") == phase]
        overview.append([phase, len(mine), *(sum(1 for r in mine if r.get("status") == s) for s in counted)])
    doc.table(["Phase", "Deliverables", *counted], overview, "Deliverables per lifecycle phase")
    add_figure(doc, brain, "lifecycle_overview", caption="Safety lifecycle overview")

    def deliverable_rows(mine: list[dict[str, Any]]) -> list[list[str]]:
        return [[
            one_line(r.get("deliverable")),
            joined(one_line(r.get("work_product_location")), flags_text(r, groups.get("location", []))),
            joined(one_line(r.get("work_product_reference")), flags_text(r, groups.get("reference", []))),
            one_line(r.get("deadline")),
            one_line(r.get("status")),
        ] for r in mine]

    def ownership_rows(mine: list[dict[str, Any]]) -> list[list[str]]:
        return [[
            one_line(r.get("deliverable")),
            joined(one_line(r.get("author")), flags_text(r, groups.get("author", []))),
            flags_text(r, groups.get("verification", [])),
            joined(one_line(r.get("gate_reviewer")), flags_text(r, groups.get("reviewer", []))),
        ] for r in mine]

    for phase in phases:
        doc.h1(phase)
        mine = [r for r in rows if r.get("lifecycle_phase") == phase]
        if not mine:
            doc.p("No deliverables recorded for this phase.")
            continue
        doc.table(["Deliverable", "Location", "Reference", "Deadline", "Status"], deliverable_rows(mine),
                  f"{phase}: deliverables")
        doc.table(["Deliverable", "Author", "Verification", "Reviewer"], ownership_rows(mine), f"{phase}: ownership")
        add_figure(doc, brain, "phase_flow", {"phase": phase.split(".", 1)[0]}, caption=f"Phase flow: {phase}")
    orphans = [r for r in rows if r.get("lifecycle_phase") not in phases]
    if orphans:
        doc.h1("Deliverables outside the lifecycle phases")
        doc.table(["Deliverable", "Phase", "Status"],
                  [[one_line(r.get("deliverable")), one_line(r.get("lifecycle_phase")), one_line(r.get("status"))]
                   for r in orphans], "Rows whose phase is not a lifecycle phase")

    doc.appendix("Roles")
    doc.p("Author roles the matrix can assign to a deliverable:")
    doc.bullets([s.header for s in groups.get("author", [])])
    doc.p("Reviewer roles:")
    doc.bullets([s.header for s in groups.get("reviewer", [])])
    doc.p("Verification levels:")
    doc.bullets([s.header for s in groups.get("verification", [])])

    doc.appendix("QMS references")
    table_or_note(
        doc, ["Document", "Link"],
        [[one_line(q.get("name")), md_link(q.get("name"), q.get("url"))] for q in brain.service("qms_document").list()],
        "Quality management system documents", "No QMS documents recorded.",
    )

    doc.appendix("Status legend")
    doc.table(["Status", "Meaning"], [[s, STATUS_MEANING.get(s, "")] for s in statuses], "Deliverable status values")
    return doc


# -- status_report ------------------------------------------------------------
@register_document(Spec(
    key="status_report", title="Status report",
    description="Row counts, open Jira tickets, tasks ending within seven days and recent changes, with the "
                "task flow and lifecycle overview diagrams.",
))
def status_report(brain: Brain, params: dict[str, str]) -> Any:
    from ..services.queries import DUE_WINDOW_DAYS, open_jira_tickets, recent_changes, tasks_due

    doc = new_document(brain, "Status Report", "report", subtitle="Working-knowledge database snapshot")
    doc.h1("Counts")
    doc.fields([(schema.label, brain.service(schema.name).count()) for schema in brain.registry], "Rows per entity")

    doc.h1("Open Jira tickets")
    table_or_note(
        doc, ["Ticket", "Status", "Link"],
        [[one_line(t.get("name")), one_line(t.get("status")), md_link(t.get("name"), t.get("url"))]
         for t in open_jira_tickets(brain)],
        "Open Jira tickets", "No open Jira tickets.",
    )

    doc.h1(f"Tasks ending within {DUE_WINDOW_DAYS} days")
    table_or_note(
        doc, ["Task", "Class", "Start", "End"],
        [[one_line(t.get("name")), one_line(t.get("task_class")), one_line(t.get("start")), one_line(t.get("end"))]
         for t in tasks_due(brain)],
        f"Tasks ending within {DUE_WINDOW_DAYS} days", "No tasks end within the window.",
    )
    add_figure(doc, brain, "task_flow", caption="Task flow by class")

    doc.h1("Recent changes")
    table_or_note(
        doc, ["When", "Actor", "Action", "Entity", "Row"],
        [[one_line(a.get("ts")), one_line(a.get("actor")), one_line(a.get("action")), one_line(a.get("entity")),
          "" if a.get("entity_id") is None else str(a["entity_id"])] for a in recent_changes(brain, 20)],
        "Last 20 audit entries", "No changes recorded yet.",
    )

    doc.h1("Safety lifecycle")
    add_figure(doc, brain, "lifecycle_overview", caption="Safety lifecycle overview")
    return doc


# -- handbook -----------------------------------------------------------------
@register_document(Spec(
    key="handbook", title="Working Knowledge Handbook",
    description="Facts, people by class, links, QMS documents, machine functions and use cases, with the schema "
                "map in an appendix.",
))
def handbook(brain: Brain, params: dict[str, str]) -> Any:
    doc = new_document(brain, "Working Knowledge Handbook", "report", subtitle="Everything the database knows")

    doc.h1("Facts")
    facts = brain.service("fact").list()
    if facts:
        doc.fields([(one_line(f.get("name")), one_line(f.get("text"))) for f in facts], "Facts")
    else:
        doc.p("No facts recorded.")

    doc.h1("People")
    people = brain.service("person").list()
    if not people:
        doc.p("No people recorded.")
    by_class: dict[str, list[dict[str, Any]]] = {}
    for person in people:
        by_class.setdefault(one_line(person.get("person_class")) or "Unclassified", []).append(person)
    for person_class, members in by_class.items():
        doc.h2(person_class)
        doc.table(["Nickname", "Text"], [[one_line(p.get("nickname")), one_line(p.get("text"))] for p in members],
                  f"People: {person_class}")

    doc.h1("Links")
    table_or_note(
        doc, ["Class", "Name", "Link"],
        [[one_line(li.get("link_class")), one_line(li.get("name")), md_link(li.get("name"), li.get("url"))]
         for li in brain.service("link").list()],
        "Links", "No links recorded.",
    )

    doc.h1("QMS documents")
    table_or_note(
        doc, ["Document", "Link"],
        [[one_line(q.get("name")), md_link(q.get("name"), q.get("url"))] for q in brain.service("qms_document").list()],
        "QMS documents", "No QMS documents recorded.",
    )

    doc.h1("Machine functions")
    table_or_note(
        doc, ["Function", "Description"],
        [[one_line(m.get("name")), one_line(m.get("description"))] for m in brain.service("machine_function").list()],
        "Wheel Loader machine functions", "No machine functions recorded.",
    )

    doc.h1("Use cases")
    table_or_note(
        doc, ["Use case", "Description"],
        [[one_line(u.get("name")), one_line(u.get("description"))] for u in brain.service("use_case").list()],
        "Wheel Loader use cases", "No use cases recorded.",
    )

    doc.appendix("Schema map")
    doc.p("The entities the database holds, with their field and row counts.")
    add_figure(doc, brain, "schema_map", caption="Entities and their row counts")
    return doc


# -- stpa_report --------------------------------------------------------------
STPA_PURPOSE = (
    "This document is a working view of one STPA analysis kept in the working-knowledge database: the "
    "hazards, the unsafe control actions by controller and category, the loss scenarios with their causal "
    "factors and constraints, every object with the citation of the Confluence page, version and section it "
    "was read from, and the page's review comments when the analysis came from an evidence bundle. It is "
    "regenerated from the database on demand; the Confluence page stays the truth for the text."
)
CATEGORY_TITLES = {
    "not_providing": "Not providing",
    "providing": "Providing",
    "timing_order": "Incorrect timing or order",
    "duration": "Stopped too soon or applied too long",
}


def codes_text(items: Any) -> str:
    return ", ".join(str(x) for x in (items or []))


def yes(value: Any) -> str:
    return "yes" if value else ""


def object_key(item: dict[str, Any]) -> str:
    """How a report names an object: its code, or ``row N`` for a scenario."""
    if item.get("code"):
        return str(item["code"])
    return f"row {item['row']}" if item.get("row") is not None else f"order {item.get('order')}"


@register_document(Spec(
    key="stpa_report", title="STPA report",
    description="One STPA analysis: hazards, the UCA table by controller and category, the loss scenarios with "
                "causal factors and constraints, the trace diagram, every object with its citation, and the "
                "page's review comments as an appendix when the analysis came from a Hopper bundle.",
    params=(Param("analysis", "The analysis: its id, uid or slug", required=True),),
))
def stpa_report(brain: Brain, params: dict[str, str]) -> Any:
    from ..stpa.stpa_factory import bundle_comments

    row = brain.stpa.resolve(params["analysis"])
    slug = row["slug"]
    parts = brain.stpa.parts(slug)
    doc = new_document(brain, f"STPA report: {row['name']}", "report", subtitle=row.get("system") or "")

    doc.h1("Purpose")
    doc.p(STPA_PURPOSE)
    doc.h1("Source")
    doc.fields([
        ("Analysis", f"{row['name']} ({slug})"),
        ("Status", one_line(row.get("status"))),
        ("Source", one_line(row.get("source_kind"))),
        ("Page", md_link(row.get("source_page_id"), row.get("source_url")) or one_line(row.get("source_page_id"))),
        ("Version", "" if row.get("source_version") is None else str(row["source_version"])),
        ("Body SHA-256", one_line(row.get("source_body_sha256"))),
        ("Taken at", one_line(row.get("source_taken_at"))),
        ("Bundle", one_line(row.get("source_bundle"))),
        ("Control structure", one_line(row.get("control_structure"))),
    ], "Where the analysis came from")

    doc.h1("Losses")
    table_or_note(doc, ["Code", "Loss"], [[x["code"], one_line(x.get("text"))] for x in parts["losses"]],
                  "Losses", "The page lists no losses.")

    doc.h1("Hazards")
    table_or_note(
        doc, ["Code", "Parent", "Hazard", "Losses", "Retired"],
        [[h["code"], one_line(h.get("parent")), one_line(h.get("text")), codes_text(h.get("losses")),
          yes(h.get("retired"))] for h in parts["hazards"]],
        "Hazards", "No hazards recorded.",
    )

    doc.h1("Unsafe control actions")
    ucas = parts["ucas"]
    if not ucas:
        doc.p("No unsafe control actions recorded.")
    by_controller: dict[str, list[dict[str, Any]]] = {}
    for u in ucas:
        by_controller.setdefault(one_line(u.get("controller")) or "Unnamed controller", []).append(u)
    categories = list(brain.lookups.get("stpa_uca_category", ()))
    for controller, mine in by_controller.items():
        doc.h2(controller)
        rows = []
        ordered = [u for c in categories for u in mine if u.get("category") == c]
        ordered += [u for u in mine if u.get("category") not in categories]
        for u in ordered:
            status = "retired" if u.get("retired") else ""
            if u.get("duplicate_of"):
                status = joined(status, f"duplicate of {u['duplicate_of']}")
            link = joined(one_line(u.get("cs_controller")), one_line(u.get("cs_signal")))
            category = u.get("category") or ""
            rows.append([u["code"], one_line(u.get("control_action")), CATEGORY_TITLES.get(category, category),
                         one_line(u.get("text")), codes_text(u.get("hazards")), status, link])
        doc.table(["UCA", "Control action", "Category", "Text", "Hazards", "Status", "Structure"], rows,
                  f"Unsafe control actions of {controller}")

    doc.h1("Loss scenarios")
    table_or_note(
        doc, ["Row", "UCA", "Counterpart", "Types", "Causal factors", "Beliefs", "Constraints"],
        [["" if s.get("row") is None else str(s["row"]), one_line(s.get("uca")), one_line(s.get("counterpart")),
          codes_text(s.get("types")), one_line(s.get("causal_factors")), one_line(s.get("beliefs")),
          codes_text(s.get("constraints"))] for s in parts["scenarios"]],
        "Loss scenarios", "No loss scenarios recorded.",
    )

    doc.h1("Constraints")
    named_by: dict[str, list[str]] = {}
    for s in parts["scenarios"]:
        for c in s.get("constraints") or []:
            named_by.setdefault(c, []).append("" if s.get("row") is None else str(s["row"]))
    table_or_note(
        doc, ["Code", "Constraint", "Scenario rows"],
        [[c["code"], one_line(c.get("text")) or "(referenced only)", ", ".join(named_by.get(c["code"], []))]
         for c in parts["constraints"]],
        "Safety constraints", "No constraints recorded.",
    )

    doc.h1("Trace")
    doc.p("Hazards, unsafe control actions, loss scenarios and constraints, with the edges the page states.")
    add_figure(doc, brain, "stpa_trace", {"analysis": slug}, caption=f"STPA trace: {row['name']}")

    doc.appendix("Citations")
    cites = []
    labels = (("hazards", "Hazard"), ("ucas", "UCA"), ("scenarios", "Scenario"), ("constraints", "Constraint"))
    for key, label in labels:
        for item in parts[key]:
            cites.append([label, object_key(item), one_line(item.get("cite"))])
    table_or_note(doc, ["Object", "Code", "Citation"], cites, "Where every object was read", "No objects to cite.")

    comments = bundle_comments(row.get("source_bundle"), row.get("source_page_id"))
    if comments:
        doc.appendix("Review comments")
        doc.p("The page comments the evidence bundle holds (footer and inline), the inline ones with the text "
              "they are anchored on; a reply follows its comment. No author is named here.")
        rows = []
        for c in comments:
            rows.append([one_line(c.get("kind")), one_line((c.get("created") or "")[:10]),
                         one_line(c.get("resolution")), one_line(c.get("selection")), one_line(c.get("body"))])
            for reply in c.get("replies") or []:
                rows.append(["reply", one_line((reply.get("created") or "")[:10]), "", "", one_line(reply.get("body"))])
        doc.table(["Kind", "Date", "State", "Anchored on", "Comment"], rows, "Review comments from the bundle")
    return doc
