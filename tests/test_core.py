from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from asi_dewey import Brain, __version__
from asi_dewey.errors import CommandError, NotFound, ValidationError
from asi_dewey.schema import UID_PATTERN, new_uid

FIXTURE_0_7_4 = Path(__file__).parent / "fixtures" / "dewey-0.7.4.db"
FIXTURE_0_8_4 = Path(__file__).parent / "fixtures" / "dewey-0.8.4.db"
FIXTURE_0_10_1 = Path(__file__).parent / "fixtures" / "dewey-0.10.1.db"  # schema 4: the thirteen tables, with rows
CS_TABLES = [
    "control_structures", "cs_controllers", "cs_algorithms", "cs_process_model_entries", "cs_edges", "cs_signals",
    "cs_notes",
]
STPA_TABLES = ["stpa_analyses", "stpa_losses", "stpa_hazards", "stpa_ucas", "stpa_scenarios", "stpa_constraints"]


def test_crud_round_trip(brain):
    created = brain.execute("create", entity="fact", data={"name": "Code", "text": "PRJ-0001", "order": "7"})
    assert created.ok, created.errors
    row = created.data
    assert row["id"] == 1 and row["order"] == 7 and row["created_at"]

    got = brain.execute("get", entity="facts", id=1)
    assert got.ok and got.data["name"] == "Code"

    updated = brain.execute("update", entity="fact", id=1, set=["text=new"])
    assert updated.ok and updated.data["text"] == "new"
    assert updated.data["updated_at"] >= row["updated_at"]

    listed = brain.execute("list", entity="fact", filter=["order=7"])
    assert listed.ok and len(listed.data) == 1

    assert brain.execute("count", entity="fact").data["count"] == 1
    assert brain.execute("delete", entity="fact", id=1).ok
    assert brain.execute("count", entity="fact").data["count"] == 0
    missing = brain.execute("get", entity="fact", id=1)
    assert not missing.ok and "not found" in missing.errors[0]


def test_validation_and_unknowns_come_back_as_results(brain):
    bad = brain.execute("create", entity="task", data={"start": "banana"})
    assert not bad.ok and any("required" in e for e in bad.errors) and any("date" in e for e in bad.errors)
    assert not brain.execute("create", entity="dragon", data={}).ok
    assert not brain.execute("fly", entity="task").ok
    assert not brain.execute("get", entity="task").ok  # missing id
    assert not brain.execute("list", entity="task", bogus=1).ok
    weird = brain.execute("create", entity="task", data={"name": "x", "task_class": "mystery"})
    assert weird.ok and weird.warnings and "lookup" in weird.warnings[0]


def test_ordering_filters_and_bools(seeded):
    rows = seeded.execute("list", entity="fact", order_by="-order").data
    assert [r["order"] for r in rows] == [2, 1]
    plan = seeded.execute("list", entity="safety_plan_row", filter=["loc_dms=1"]).data
    assert len(plan) == 1 and plan[0]["loc_dms"] is True and plan[0]["loc_jama"] is False
    assert seeded.execute("list", entity="safety_plan_row", filter=["loc_jama=true"]).data == []
    task = seeded.execute("list", entity="task").data[0]
    assert task["start"] == "2026-10-20" and task["end"] == "2026-10-23"


def test_audit_log_and_events(brain):
    seen = []
    brain.events.subscribe("*", lambda topic, event: seen.append(topic))
    brain.execute("create", entity="fact", data={"name": "a"}, actor="ai")
    brain.execute("update", entity="fact", id=1, data={"text": "b"}, actor="human")
    brain.execute("delete", entity="fact", id=1)
    tail = brain.storage.audit_tail(10)
    assert [t["action"] for t in tail] == ["delete", "update", "create"]
    assert [t["actor"] for t in tail] == ["python", "human", "ai"]
    assert seen == ["entity.created", "entity.updated", "entity.deleted"]


def test_schema_and_status_commands(seeded):
    status = seeded.execute("status").data
    assert status["app_version"] == __version__
    assert status["entities"]["fact"] == 2 and "create" in status["commands"]
    full = seeded.execute("schema").data
    assert len(full["entities"]) == 9 and "task_class" in full["lookups"] and full["commands"]
    one = seeded.execute("schema", entity="jira").data
    assert one["name"] == "jira_ticket" and one["lookups"]["jira_status"]


def test_execute_dict_wire_format(brain):
    result = brain.execute_dict({"verb": "create", "args": {"entity": "fact", "data": {"name": "w"}}, "actor": "bot"})
    assert result.ok and result.verb == "create"
    assert brain.storage.audit_tail(1)[0]["actor"] == "bot"
    assert not brain.execute_dict({"nope": 1}).ok
    assert result.to_json(indent=None).startswith('{"ok": true')


def test_models_factory(brain):
    Fact = brain.models.build("fact")
    fact = Fact(name="n")
    assert fact.to_dict()["name"] == "n" and fact.id is None
    Row = brain.models.build("safety_plan_row")
    assert Row().loc_dms is False and Row.__schema__.name == "safety_plan_row"


def test_reopen_keeps_data_and_migrates(tmp_path):
    db = tmp_path / "persist.db"
    with Brain(db) as b:
        b.execute("create", entity="fact", data={"name": "keep"})
    with Brain(db) as b:
        assert b.execute("count", entity="fact").data["count"] == 1
        assert b.migration["created"] == []


def test_load_config_reads_jira_live_jql_and_ignores_the_retired_autofetch_key(tmp_path):
    from asi_dewey.brain import load_config

    config = tmp_path / "dewey.toml"
    config.write_text('jira_live_jql = " project = HWL "\njira_live_autofetch = true\n', encoding="utf-8")
    loaded = load_config(config)
    assert loaded["jira_live_jql"] == "project = HWL"
    assert "jira_live_autofetch" not in loaded  # the key of 0.7.3 to 0.8.0 is ignored: its window is gone (0.8.1)
    config.write_text("jira_jql = 'project = HWL'\n", encoding="utf-8")
    assert "jira_live_jql" not in load_config(config)


# -- the hidden identity (0.8.0, docs/hidden-identity-plan.md) ---------------------------------
def test_create_assigns_a_uid_once_and_keeps_a_given_one(brain):
    row = brain.execute("create", entity="fact", data={"name": "a"}).data
    assert UID_PATTERN.match(row["uid"]) and len(row["uid"]) == 36
    assert brain.execute("get", entity="fact", id=row["id"]).data["uid"] == row["uid"]
    given = new_uid()
    kept = brain.execute("create", entity="fact", data={"name": "b", "uid": "{" + given.upper() + "}"}).data
    assert kept["uid"] == given  # normalised, then kept
    assert brain.storage.audit_tail(1)[0]["payload"]["uid"] == given  # the trace is in the audit log
    other = brain.execute("create", entity="link", data={"name": "c"}).data
    assert other["uid"] != row["uid"] != kept["uid"]
    bad = brain.execute("create", entity="fact", data={"name": "d", "uid": "nope"})
    assert not bad.ok and bad.errors == ["uid: 'nope' is not a uid (a lowercase UUID4 with dashes, 36 characters)"]
    listed = brain.execute("list", entity="fact", filter=[f"uid={given.upper()}"]).data
    assert [r["id"] for r in listed] == [kept["id"]]


def test_update_refuses_to_change_the_uid_and_accepts_the_same_one(brain):
    row = brain.execute("create", entity="fact", data={"name": "a"}).data
    refused = brain.execute("update", entity="fact", id=row["id"], set=[f"uid={new_uid()}"])
    assert not refused.ok and refused.errors == ["uid is immutable"]
    assert brain.execute("get", entity="fact", id=row["id"]).data["uid"] == row["uid"]
    same = brain.execute("update", entity="fact", id=row["id"], data={"uid": row["uid"].upper(), "text": "t"})
    assert same.ok and same.data["uid"] == row["uid"] and same.data["text"] == "t"
    assert brain.storage.audit_tail(1)[0]["payload"] == {"text": "t"}  # the no-op uid is not audited as a change
    with pytest.raises(ValidationError, match="uid is immutable"):
        brain.service("fact").update(row["id"], {"uid": None})
    with pytest.raises(NotFound):
        brain.service("fact").update(999, {"uid": row["uid"]})


def test_two_rows_cannot_share_a_uid(brain):
    row = brain.execute("create", entity="fact", data={"name": "a"}).data
    twin = brain.execute("create", entity="fact", data={"name": "b", "uid": row["uid"]})
    assert not twin.ok and twin.errors == [f"uid {row['uid']} is already used by another row"]
    assert brain.execute("count", entity="fact").data["count"] == 1
    assert brain.execute("create", entity="link", data={"name": "c", "uid": row["uid"]}).ok  # per table
    for schema in brain.registry:  # the unique index on every table
        indexes = brain.storage.fetchall(f'PRAGMA index_list("{schema.table}")')
        assert [(i["name"], i["unique"]) for i in indexes if i["name"] == f"ix_{schema.table}_uid"] == [
            (f"ix_{schema.table}_uid", 1)
        ]


def test_get_by_uid_and_resolve(brain):
    service = brain.service("fact")
    row = brain.execute("create", entity="fact", data={"name": "a"}).data
    assert service.get_by_uid(row["uid"]) == row and service.get_by_uid("{" + row["uid"].upper() + "}") == row
    assert service.resolve(row["id"]) == row["id"] == service.resolve(str(row["id"]))
    assert service.resolve(row["uid"]) == row["id"] == service.resolve(row["uid"].upper())
    with pytest.raises(NotFound, match="fact uid .* not found"):
        service.get_by_uid(new_uid())
    with pytest.raises(NotFound):
        service.resolve(new_uid())
    with pytest.raises(CommandError, match="neither an id nor a uid"):
        service.resolve("abc")
    assert service.repo.get_by_uid("nope") is None and service.repo.get_by_uid(None) is None


def _rows_without_uid(db: Path) -> dict[str, list[dict]]:
    """Every entity row of every table, read with sqlite3 directly, ``uid`` dropped."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        return {
            name: [{k: v for k, v in dict(r).items() if k != "uid"} for r in con.execute(f'SELECT * FROM "{name}"')]
            for name in names
            if name not in ("schema_migrations", "audit_log", "sqlite_sequence")
        }
    finally:
        con.close()


def _columns(db: Path, table: str) -> set[str]:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
    finally:
        con.close()


def test_a_0_7_4_database_opens_as_0_8_0_with_every_row_identified(tmp_path):
    db = tmp_path / "dewey.db"
    shutil.copy(FIXTURE_0_7_4, db)
    before = _rows_without_uid(db)
    assert len(before["facts"]) == 2 and len(before["links"]) == 1 and len(before["qms_documents"]) == 1
    assert "uid" not in _columns(db, "facts") and len(before) == 9
    with Brain(db) as b:
        # 0.11.0 creates none of the thirteen tables of 0.9.0 to 0.10.1 (asi_kletz's now): the nine are altered
        assert b.migration["created"] == []
        assert b.migration["uids_stamped"] == {"fact": 2, "link": 1, "qms_document": 1}
        assert set(b.migration["altered"]) == {s.table for s in b.registry}
        assert all(cols == ["uid"] for cols in b.migration["altered"].values())
        uids: dict[tuple[str, int], str] = {}
        for schema in b.registry:
            assert "uid" in _columns(db, schema.table)
            indexes = b.storage.fetchall(f'PRAGMA index_list("{schema.table}")')
            assert (f"ix_{schema.table}_uid", 1) in [(i["name"], i["unique"]) for i in indexes]
            for row in b.service(schema.name).list():
                assert UID_PATTERN.match(row["uid"]), (schema.name, row)
                uids[(schema.name, row["id"])] = row["uid"]
        assert len(uids) == 4 and len(set(uids.values())) == 4
        stamped = [a for a in b.storage.audit_tail(50) if a["action"] == "stamp_uids"]
        assert sorted((a["entity"], a["payload"]["count"]) for a in stamped) == [
            ("fact", 2), ("link", 1), ("qms_document", 1),
        ]
        assert {a["actor"] for a in stamped} == {"system"} and all(a["entity_id"] is None for a in stamped)
        migrations = b.storage.fetchall("SELECT app_version FROM schema_migrations ORDER BY version")
        assert [m["app_version"] for m in migrations] == ["0.7.4", __version__]  # the fingerprint changed
    after = _rows_without_uid(db)
    assert {k: v for k, v in after.items() if k in before} == before  # nothing else changed, timestamps alike
    assert set(after) == set(before)  # no table added
    # a second open stamps nothing and audits nothing
    with Brain(db) as b:
        assert b.migration["uids_stamped"] == {} and b.migration["altered"] == {}
        for (name, row_id), uid in uids.items():
            assert b.execute("get", entity=name, id=row_id).data["uid"] == uid
        assert len([a for a in b.storage.audit_tail(50) if a["action"] == "stamp_uids"]) == 3
        assert len(b.storage.fetchall("SELECT 1 FROM schema_migrations")) == 2


def _versions(b: Brain) -> list[str]:
    return [m["app_version"] for m in b.storage.fetchall("SELECT app_version FROM schema_migrations ORDER BY version")]


def test_a_0_10_1_database_opens_as_0_11_0_with_the_thirteen_tables_kept(tmp_path):
    """Schema 4 to 5: the control structures and the STPA analyses are asi_kletz's, so their tables leave
    the registry; they are neither dropped nor touched, so nothing is lost before `handover` has run."""
    db = tmp_path / "dewey.db"
    shutil.copy(FIXTURE_0_10_1, db)
    before = _rows_without_uid(db)
    assert set(CS_TABLES + STPA_TABLES) <= set(before) and len(before) == 22
    assert len(before["cs_controllers"]) == 11 and len(before["stpa_ucas"]) == 8 and len(before["facts"]) == 2
    with Brain(db) as b:
        assert b.migration["created"] == [] and b.migration["altered"] == {} and b.migration["uids_stamped"] == {}
        assert len(b.registry) == 9 and b.status()["schema_version"] == 5 and len(b.status()["entities"]) == 9
        assert _versions(b) == ["0.9.0", "0.10.1", __version__]  # the fingerprint changed: one migration row
        with pytest.raises(NotFound):
            b.registry.get("control_structure")
        assert not b.execute("list", entity="stpa_uca").ok and not b.execute("cs", action="list").ok
        assert b.execute("list", entity="fact").data[0]["name"] == "Project code"
        assert b.execute("handover", out=str(tmp_path / "hand")).data["counts"]["stpa_uca"] == 8
    assert _rows_without_uid(db) == before  # every table as it was, the thirteen included
    with Brain(db) as b:
        assert b.migration["created"] == [] and len(_versions(b)) == 3


def test_a_0_8_4_database_opens_as_0_11_0_without_the_thirteen_tables(tmp_path):
    db = tmp_path / "dewey.db"
    shutil.copy(FIXTURE_0_8_4, db)
    before = _rows_without_uid(db)
    assert "control_structures" not in before and len(before) == 9
    with Brain(db) as b:
        assert b.migration["created"] == [] and b.migration["altered"] == {} and b.migration["uids_stamped"] == {}
        assert _versions(b) == ["0.8.4"]  # the same nine entities as 0.8.4: the same fingerprint, no migration row
        refused = b.execute("handover", out=str(tmp_path / "hand"))
        assert not refused.ok and refused.errors[0].startswith("nothing to hand over")
    assert _rows_without_uid(db) == before
