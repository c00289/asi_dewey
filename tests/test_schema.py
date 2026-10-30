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
    new_uid,
    normalise_uid,
    uid_field,
)
from asi_dewey.schema.fields import UID_PATTERN


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
    assert len(default_registry) == 9  # the 9 of 0.8.x; the 13 of 0.9.0 to 0.10.1 are asi_kletz's since 0.11.0


def test_safety_plan_matrix_fields_are_unique_and_grouped():
    schema = default_registry.get("safety_plan_row")
    names = schema.field_names
    assert len(names) == len(set(names)) == 64 and names[-1] == "uid"  # 63 of the sheet plus the uid (0.8.0)
    assert len(schema.visible_fields) == 63
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
    assert reg.get("widgets").fields[-1] == uid_field()  # appended: a caller's entity carries the uid too


# -- the hidden identity (0.8.0, docs/hidden-identity-plan.md) ---------------------------------
def test_every_entity_ends_with_a_hidden_uid():
    for schema in default_registry:
        last = schema.fields[-1]
        assert last.name == "uid" and last.hidden and last.type is FieldType.TEXT and last.header == "uid"
        assert [f.name for f in schema.fields].count("uid") == 1
        assert "uid" not in [f.name for f in schema.visible_fields]
        assert schema.visible_fields == schema.fields[:-1]
        assert schema.all_columns[-3] == "uid"  # id, the fields, created_at, updated_at
    assert default_registry.get("task").field("uid").to_dict()["hidden"] is True
    assert default_registry.get("task").field("name").to_dict()["hidden"] is False


def test_a_declared_uid_must_be_last_hidden_text():
    fields = (FieldSpec("uid", FieldType.TEXT, "uid", hidden=True), FieldSpec("a"))
    with pytest.raises(ValueError, match="must be the last field"):
        EntitySchema("x", "xs", "X", "x", fields)
    with pytest.raises(ValueError, match="hidden TEXT"):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("a"), FieldSpec("uid", FieldType.TEXT, "uid")))
    with pytest.raises(ValueError, match="hidden TEXT"):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("a"), FieldSpec("uid", FieldType.INT, "uid", hidden=True)))
    explicit = EntitySchema("x", "xs", "X", "x", (FieldSpec("a"), uid_field()))
    assert explicit.field_names == ("a", "uid") and EntitySchema("y", "ys", "Y", "y", ()).field_names == ("uid",)


def test_uid_coercion_accepts_canonical_normalises_case_and_braces_rejects_the_rest():
    uid = new_uid()
    assert len(uid) == 36 and UID_PATTERN.match(uid) and uid == uid.lower()
    field = uid_field()
    assert coerce(field, uid) == (uid, None)
    assert coerce(field, uid.upper()) == (uid, None)
    assert coerce(field, "{" + uid.upper() + "}") == (uid, None)
    assert coerce(field, "  " + uid + "  ") == (uid, None)
    assert coerce(field, None) == (None, None) and coerce(field, "") == (None, None)  # absent: the service assigns one
    for bad in ("not-a-uid", uid[:-1], uid.replace("-", ""), "urn:uuid:" + uid, 12):
        with pytest.raises(ValueError, match="uid: .* is not a uid"):
            coerce(field, bad)
        assert normalise_uid(bad) is None
    # a version-1 or a non-RFC-variant UUID is not a uid of ours
    assert normalise_uid("12345678-1234-1234-1234-123456789abc") is None
    assert normalise_uid(uid[:19] + "c" + uid[20:]) is None
    schema = default_registry.get("fact")
    with pytest.raises(ValidationError) as info:
        schema.coerce_row({"name": "n", "uid": "nope"})
    assert info.value.errors == ["uid: 'nope' is not a uid (a lowercase UUID4 with dashes, 36 characters)"]
    assert schema.coerce_row({"name": "n", "uid": "{" + uid.upper() + "}"})[0]["uid"] == uid
