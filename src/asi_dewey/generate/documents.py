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
from .base import Spec
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
