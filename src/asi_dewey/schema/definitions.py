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

T, M, I, B, D, U, E, J = (  # noqa: E741
    FieldType.TEXT, FieldType.MULTILINE, FieldType.INT, FieldType.BOOL,
    FieldType.DATE, FieldType.URL, FieldType.ENUM, FieldType.JSON,
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
# control structures (docs/control-structure-plan.md, section 2): the box kinds are asi_escher's
# CONTROL_NODE_KINDS, the arrow kinds its CONTROL_EDGE_KINDS; the service refuses a value outside them
CS_STATUSES = ("Draft", "Reviewed", "Baselined")
CS_CONTROLLER_KINDS = (
    "controller", "human_controller", "controlled_process", "environment", "sensor", "actuator", "external_system",
)
CS_EDGE_KINDS = ("control_action", "feedback")
default_lookups.register("cs_status", CS_STATUSES)
default_lookups.register("cs_controller_kind", CS_CONTROLLER_KINDS)
default_lookups.register("cs_edge_kind", CS_EDGE_KINDS)

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

# -- STPA control structures ---------------------------------------------------
# One structure holds everything; every part names its structure by slug and its parent by key, so
# the rows survive any export and import (a workbook sheet carries no id column) and a later STPA
# step can point at a controller by key and a signal by its id (docs/control-structure-plan.md, 2).
STRUCTURE = FieldSpec(
    "structure", T, "structure", required=True, help="Slug of the control structure this row belongs to",
)

CONTROL_STRUCTURE = register_entity(EntitySchema(
    name="control_structure", table="control_structures", label="Control Structure", sheet="CS structures",
    description=(
        "An STPA control structure: the controllers, their algorithms and process models, the control actions "
        "and feedback between them. Built by the factory, drawn by asi_escher, exported as draw.io, PNG and SVG."
    ),
    order_by=("name", "id"),
    fields=(
        FieldSpec("name", T, "name", required=True),
        FieldSpec("slug", T, "slug", help="Stable key the parts point at; unique; from the name when not given"),
        FieldSpec("system", T, "system", help="The system the structure controls, e.g. an autonomous loader"),
        FieldSpec("description", M, "description"),
        FieldSpec("source", T, "source", help="The file it came from, or 'built by hand'"),
        FieldSpec("status", E, "status", lookup="cs_status"),
        FieldSpec("revision", I, "revision"),
    ),
))

CS_CONTROLLER = register_entity(EntitySchema(
    name="cs_controller", table="cs_controllers", label="CS Controller", sheet="CS controllers",
    description=(
        "A box of a control structure: a controller, a human controller, the controlled process, "
        "the environment, a sensor, an actuator or an external system."
    ),
    order_by=("structure", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("order", I, "order", help="Top of the hierarchy first"),
        FieldSpec("key", T, "key", help="Stable slug within the structure; from the name if empty"),
        FieldSpec("name", T, "name", required=True),
        FieldSpec("kind", E, "kind", lookup="cs_controller_kind"),
        FieldSpec("responsibility", M, "responsibility"),
        FieldSpec("process_model_title", T, "process model title"),
        FieldSpec("note", M, "note"),
    ),
))

CS_ALGORITHM = register_entity(EntitySchema(
    name="cs_algorithm", table="cs_algorithms", label="CS Algorithm", sheet="CS algorithms",
    description="A control algorithm of a controller (V1, S3 ...), drawn in the orange section of its box.",
    order_by=("structure", "controller", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("controller", T, "controller", required=True, help="Key of the controller that owns it"),
        FieldSpec("order", I, "order"),
        FieldSpec("code", T, "code", required=True, help="V1, S3 ..."),
        FieldSpec("name", T, "name"),
    ),
))

CS_PROCESS_MODEL_ENTRY = register_entity(EntitySchema(
    name="cs_process_model_entry", table="cs_process_model_entries", label="CS Process Model Entry",
    sheet="CS process model",
    description=(
        "One entry of a controller's process model: a heading naming control actions, the variables "
        "the decision depends on, the feedback that updates them."
    ),
    order_by=("structure", "controller", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("controller", T, "controller", required=True, help="Key of the controller that owns it"),
        FieldSpec("order", I, "order"),
        FieldSpec("heading", T, "heading"),
        FieldSpec("control_actions", J, "control actions", help="Signal ids, one per line"),
        FieldSpec("variables", J, "variables", help="One per line"),
        FieldSpec("updated_by", J, "updated by", help="Signal ids, one per line"),
        FieldSpec("references", J, "references", help="Every signal id the entry mentions, one per line"),
    ),
))

CS_EDGE = register_entity(EntitySchema(
    name="cs_edge", table="cs_edges", label="CS Edge", sheet="CS edges",
    description=(
        "An arrow between two controllers carrying signals: a control action down the hierarchy or feedback up."
    ),
    order_by=("structure", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("order", I, "order"),
        FieldSpec("key", T, "key", help="Stable key within the structure, e.g. e7; the next free one when not given"),
        FieldSpec("kind", E, "kind", lookup="cs_edge_kind"),
        FieldSpec("source", T, "source", required=True, help="Key of the controller the arrow leaves"),
        FieldSpec("target", T, "target", required=True, help="Key of the controller the arrow enters"),
    ),
))

CS_SIGNAL = register_entity(EntitySchema(
    name="cs_signal", table="cs_signals", label="CS Signal", sheet="CS signals",
    description="One line on an arrow: CA-xx a control action, FB-xx feedback, with its name.",
    order_by=("structure", "edge", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("edge", T, "edge", required=True, help="Key of the edge that carries it"),
        FieldSpec("order", I, "order"),
        FieldSpec("signal_id", T, "signal id", required=True, help="CA-01, FB-12 ..."),
        FieldSpec("kind", E, "kind", lookup="cs_edge_kind", help="Defaults to the edge's kind and must match it"),
        FieldSpec("name", T, "name"),
        FieldSpec("placeholder", B, "placeholder", help="A signal still to be numbered"),
    ),
))

CS_NOTE = register_entity(EntitySchema(
    name="cs_note", table="cs_notes", label="CS Note", sheet="CS notes",
    description="A free-standing text of a control structure, floating beside a controller when attached to one.",
    order_by=("structure", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("order", I, "order"),
        FieldSpec("text", M, "text", required=True),
        FieldSpec("attached_to", T, "attached to", help="Key of the controller it floats beside, or empty"),
    ),
))

CS_ENTITIES = (
    CONTROL_STRUCTURE, CS_CONTROLLER, CS_ALGORITHM, CS_PROCESS_MODEL_ENTRY, CS_EDGE, CS_SIGNAL, CS_NOTE,
)
ALL_ENTITIES = (
    TASK, FACT, MACHINE_FUNCTION, USE_CASE, LINK, JIRA_TICKET, QMS_DOCUMENT, PERSON, SAFETY_PLAN_ROW, *CS_ENTITIES,
)
