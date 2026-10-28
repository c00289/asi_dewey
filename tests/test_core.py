from __future__ import annotations

from asi_dewey import Brain, __version__


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


def test_load_config_reads_the_jira_live_keys(tmp_path):
    from asi_dewey.brain import load_config

    config = tmp_path / "dewey.toml"
    config.write_text('jira_live_jql = " project = HWL "\njira_live_autofetch = false\n', encoding="utf-8")
    loaded = load_config(config)
    assert loaded["jira_live_jql"] == "project = HWL" and loaded["jira_live_autofetch"] is False
    config.write_text('jira_live_autofetch = "false"\n', encoding="utf-8")  # a string is not a boolean: ignored
    loaded = load_config(config)
    assert "jira_live_autofetch" not in loaded and "jira_live_jql" not in loaded
    config.write_text("jira_live_autofetch = true\n", encoding="utf-8")
    assert load_config(config)["jira_live_autofetch"] is True
