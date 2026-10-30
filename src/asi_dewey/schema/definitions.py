"""The built-in entities, seeded from the sheets of ``dewey.xlsx``.

Importing this module registers every entity and lookup with the default
registries. Column labels are the exact workbook headers so the Excel export
reproduces the familiar sheets and the Excel import can read them back. Every entity ends with
the hidden ``uid`` field, appended by ``EntitySchema`` (docs/hidden-identity-plan.md, 3.1).
"""

from __future__ import annotations

from .entity import EntitySchema, flag_fields
from .fields import FieldSpec, FieldType
from .lookups import default_lookups
from .registry import register_entity

T, M, I, D, U, E = (  # noqa: E741
    FieldType.TEXT, FieldType.MULTILINE, FieldType.INT, FieldType.DATE, FieldType.URL, FieldType.ENUM,
)

# -- lookups ----------------------------------------------------------------
LIFECYCLE_PHASES = (
    "1. Concept Development",
    "2. HARA / Risk Assessment",
    "3. Functional Safety Concept (FSC)",
    "4. System Design and Development",
    "5. HW & SW Design and Development",
    "6. Integration and Testing",
    "7. Safety Validation",
    "8. Functional Safety Assessment",
    "9. Production and Operation",
    "10. Decommissioning",
)

default_lookups.register("task_class", ("administrative", "status", "deliverable", "review"))
default_lookups.register("link_class", ("IT", "MS Windows software", "tool", "n.a."))
default_lookups.register("jira_status", ("open", "in progress", "blocked", "done"))
default_lookups.register("pdp_phase", ("1", "2", "3", "4", "5", "6"))
default_lookups.register("lifecycle_phase", LIFECYCLE_PHASES)
default_lookups.register("plan_status", ("Pending", "Ongoing", "Blocked", "Alternative", "Out-of-Scope", "Done"))

# -- simple entities ----------------------------------------------------------
TASK = register_entity(EntitySchema(
    name="task", table="tasks", label="Task", sheet="tasks",
    description="Things the engineer has to do or has done, with a class, dates, and comments.",
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", I, "task order"),
        FieldSpec("task_class", E, "task class", lookup="task_class"),
        FieldSpec("name", T, "task name", required=True),
        FieldSpec("start", D, "task start"),
        FieldSpec("end", D, "task end"),
        FieldSpec("comments", M, "task comments"),
    ),
))

FACT = register_entity(EntitySchema(
    name="fact", table="facts", label="Fact", sheet="facts",
    description="Named facts worth remembering (project codes, definitions, stakeholders).",
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", I, "fact order"),
        FieldSpec("name", T, "fact name", required=True),
        FieldSpec("text", M, "fact text"),
    ),
))

MACHINE_FUNCTION = register_entity(EntitySchema(
    name="machine_function", table="machine_functions", label="Machine Function", sheet="WL functions",
    description="Wheel Loader machine functions and their descriptions.",
    order_by=("name", "id"),
    fields=(
        FieldSpec("name", T, "function name", required=True),
        FieldSpec("description", M, "function description"),
    ),
))

USE_CASE = register_entity(EntitySchema(
    name="use_case", table="use_cases", label="Use Case", sheet="WL use cases",
    description="Wheel Loader operational use cases.",
    order_by=("name", "id"),
    fields=(
        FieldSpec("name", T, "use case name", required=True),
        FieldSpec("description", M, "use case description"),
    ),
))

LINK = register_entity(EntitySchema(
    name="link", table="links", label="Link", sheet="links",
    description="Bookmarks: tools, boards, documents.",
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", I, "link order"),
        FieldSpec("link_class", E, "link class", lookup="link_class"),
        FieldSpec("name", T, "link name", required=True),
        FieldSpec("url", U, "link text"),
    ),
))

JIRA_TICKET = register_entity(EntitySchema(
    name="jira_ticket", table="jira_tickets", label="Jira Ticket", sheet="JIRA",
    description=(
        "Jira tickets the engineer owns or tracks. Rows with a key are a cached view of Jira, "
        "refreshed by `jira sync` through asi_hopper; rows without a key are typed by hand."
    ),
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", I, "JIRA order"),
        FieldSpec("name", T, "JIRA name", required=True),
        FieldSpec("status", E, "JIRA status", lookup="jira_status"),
        FieldSpec("url", U, "JIRA link"),
        # filled by `jira sync` (asi_hopper); all optional so hand-typed rows and old workbooks still load
        FieldSpec("key", T, "JIRA key", group="sync", help="Issue key, e.g. HWL-2572; the upsert key for jira sync"),
        FieldSpec("issue_type", T, "JIRA type", group="sync"),
        FieldSpec("priority", T, "JIRA priority", group="sync"),
        FieldSpec("assignee", T, "JIRA assignee", group="sync"),
        FieldSpec("parent_key", T, "JIRA parent", group="sync", help="Epic or parent issue key"),
        FieldSpec("labels", T, "JIRA labels", group="sync", help="Semicolon-separated"),
        FieldSpec("updated", T, "JIRA updated", group="sync", help="Jira's last-updated timestamp"),
        FieldSpec("synced_at", T, "JIRA synced", group="sync", help="When jira sync last wrote this row"),
    ),
))

QMS_DOCUMENT = register_entity(EntitySchema(
    name="qms_document", table="qms_documents", label="QMS Document", sheet="QMS",
    description="Quality management system references (QM, QP, QF documents).",
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", I, "QMS order"),
        FieldSpec("name", T, "QMS name", required=True),
        FieldSpec("url", U, "QMS link"),
    ),
))

PERSON = register_entity(EntitySchema(
    name="person", table="people", label="Person", sheet="people",
    description="People the engineer works with, by role, with contact text.",
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", I, "people order"),
        FieldSpec("person_class", T, "people class"),
        FieldSpec("nickname", T, "people nickname", required=True),
        FieldSpec("text", T, "people text"),
    ),
))

# -- safety plan matrix --------------------------------------------------------
LOCATION_FLAGS = ("DMS", "JAMA", "Sharepoint")
REFERENCE_FLAGS = (
    "Foundational RA", "PDP/QF", "PDP-16", "PDP-17", "Platform FSC", "Platform TSC",
    "QF-12", "QF-17", "QF-18", "QF-19", "QF-FSA Report", "QF-Safety Case",
    "QM/QP-Risk Assessment Plan", "QM-Production Plan", "QM-Validation Plan",
    "QP-06", "QP-11", "QP-12", "QP-31", "QP-32", "QP-FSA", "Scope Definition", "Supplier",
)
AUTHOR_FLAGS = (
    "Dev Manager", "Electronics Engineer (Mechanical and Electrical)", "Embedded Software Engineer",
    "FuSa Engineer", "Mechatronics Software Engineer", "Mechatronics Systems Engineer",
    "Product Manager", "Production Team", "Reliability Engineer", "Respective Robot Team Member",
    "Robot Chief", "System Architect", "Tech Lead - Occupational Safety", "V&V Team",
    "Independent Reviewer", "ASI STPA Practitioners", "Tech Lead - Functional Safety",
)
VERIFICATION_FLAGS = ("Level U3 (refer section 3.2)", "QP-06 Review Process", "Scope Definition Review")
REVIEWER_FLAGS = (
    "Tech Lead - Functional Safety", "Tech Lead - Occupational Safety", "Tech Lead - Respective Area",
    "Tech Lead - Safety and Compliance", "Tech Lead - Systems", "PAT", "Technical Training Team",
)

SAFETY_PLAN_ROW = register_entity(EntitySchema(
    name="safety_plan_row", table="safety_plan", label="Safety Plan Row", sheet="Safety Plan",
    description=(
        "One deliverable of the platform safety plan: lifecycle phase, where the work product "
        "lives, which QMS documents it references, who authors, verifies, and reviews it."
    ),
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", I, "order"),
        FieldSpec("pdp_phase", E, "PDP Phases", lookup="pdp_phase"),
        FieldSpec("lifecycle_phase", E, "Safety Lifecycle Phase", lookup="lifecycle_phase"),
        FieldSpec("deliverable", M, "Safety Deliverables", required=True),
        FieldSpec("work_product_location", T, "Work Product Location"),
        *flag_fields("location", "loc", LOCATION_FLAGS),
        FieldSpec("work_product_reference", T, "Work Product Reference"),
        *flag_fields("reference", "ref", REFERENCE_FLAGS),
        FieldSpec("author", T, "Author", group="author"),
        *flag_fields("author", "author", AUTHOR_FLAGS),
        *flag_fields("verification", "verify", VERIFICATION_FLAGS),
        FieldSpec("gate_reviewer", T, "Gate Reviewer", group="reviewer"),
        *flag_fields("reviewer", "reviewer", REVIEWER_FLAGS),
        FieldSpec("deadline", T, "Expected Duration/Deadline"),
        FieldSpec("status", E, "Status (Pending/ Ongoing/ Blocked/ Alternative/Out-of-Scope/ Done)",
                  lookup="plan_status"),
    ),
))

# The seven control-structure entities (0.9.0) and the six STPA entities (0.10.0) are asi_kletz's since
# 0.11.0 (the owner, 2026-10-29: "move everything to Kletz"); their tables stay in an older database,
# unregistered, until `handover` has carried them over (handover.py holds their frozen shape).
ALL_ENTITIES = (
    TASK, FACT, MACHINE_FUNCTION, USE_CASE, LINK, JIRA_TICKET, QMS_DOCUMENT, PERSON, SAFETY_PLAN_ROW,
)
