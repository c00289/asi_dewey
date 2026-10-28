from __future__ import annotations

import datetime as dt

import pytest

from asi_dewey.errors import NotFound, ValidationError
from asi_dewey.schema import (
    EntitySchema,
    FieldSpec,
    FieldType,
    SchemaRegistry,
    coerce,
    default_lookups,
    default_registry,
    definitions,  # noqa: F401
    flag_fields,
)


def spec(kind, **kw):
    return FieldSpec("f", kind, **kw)


def test_coerce_int_bool_date():
    assert coerce(spec(FieldType.INT), "3") == (3, None)
    assert coerce(spec(FieldType.INT), 3.0) == (3, None)
    with pytest.raises(ValueError):
        coerce(spec(FieldType.INT), "three")
    assert coerce(spec(FieldType.BOOL), None) == (False, None)
    assert coerce(spec(FieldType.BOOL), "x") == (True, None)
    assert coerce(spec(FieldType.BOOL), 0) == (False, None)
    assert coerce(spec(FieldType.DATE), 46314) == ("2026-10-19", None)
    assert coerce(spec(FieldType.DATE), "10/23/2026") == ("2026-10-23", None)
    assert coerce(spec(FieldType.DATE), dt.datetime(2026, 1, 2, 3, 4)) == ("2026-01-02", None)
    with pytest.raises(ValueError):
        coerce(spec(FieldType.DATE), "someday")


def test_coerce_text_and_enum_warning():
    assert coerce(spec(FieldType.TEXT), "  a\xa0b  ") == ("a b", None)
    assert coerce(spec(FieldType.MULTILINE), "a\nb ") == ("a\nb", None)
    with pytest.raises(ValueError):
        coerce(spec(FieldType.TEXT, required=True), "   ")
    value, warning = coerce(spec(FieldType.ENUM, lookup="task_class"), "weird", default_lookups)
    assert value == "weird" and "not in lookup" in warning
    assert coerce(spec(FieldType.ENUM, lookup="task_class"), "status", default_lookups) == ("status", None)


def test_schema_validation_collects_all_errors():
    schema = default_registry.get("task")
    with pytest.raises(ValidationError) as info:
        schema.coerce_row({"name": "", "start": "nope", "bogus": 1})
    messages = " | ".join(info.value.errors)
    assert "required" in messages and "not a date" in messages and "unknown field" in messages


def test_registry_aliases_and_fingerprint():
    assert default_registry.get("WL functions").name == "machine_function"
    assert default_registry.get("Safety Plan").table == "safety_plan"
    assert default_registry.get("JIRA").name == "jira_ticket"
    with pytest.raises(NotFound):
        default_registry.get("unicorns")
    assert default_registry.fingerprint() == default_registry.fingerprint()
    assert len(default_registry) == 9


def test_safety_plan_matrix_fields_are_unique_and_grouped():
    schema = default_registry.get("safety_plan_row")
    names = schema.field_names
    assert len(names) == len(set(names)) == 63
    groups = schema.groups()
    assert len(groups["reference"]) == 23 and len(groups["author"]) == 18 and len(groups["reviewer"]) == 8
    assert "author_tech_lead_functional_safety" in names and "reviewer_tech_lead_functional_safety" in names
    assert schema.field("author_v_v_team").header == "V&V Team"


def test_entity_schema_rejects_duplicates_and_system_names():
    with pytest.raises(ValueError):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("a"), FieldSpec("a")))
    with pytest.raises(ValueError):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("id"),))
    with pytest.raises(ValueError):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("a"),), order_by=("nope",))


def test_custom_registry_is_independent():
    reg = SchemaRegistry()
    fields = (FieldSpec("name"), *flag_fields("g", "g", ["A B"]))
    reg.register(EntitySchema("widget", "widgets", "Widget", "widgets", fields))
    assert reg.get("widgets").field("g_a_b").type is FieldType.BOOL
    assert "task" not in reg
