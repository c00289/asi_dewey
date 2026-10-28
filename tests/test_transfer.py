from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook

from asi_dewey import Brain
from asi_dewey.schema import UID_PATTERN, new_uid
from tests.conftest import WORKBOOK


def test_json_dump_and_load_modes(seeded, tmp_path):
    out = tmp_path / "dump.json"
    dumped = seeded.execute("dump", out=str(out))
    assert dumped.ok and dumped.data["entities"]["fact"] == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2 and set(payload["entities"]) >= {"fact", "task", "safety_plan_row"}

    with Brain(tmp_path / "other.db") as other:
        loaded = other.execute("load", path=str(out), mode="replace")
        assert loaded.ok, loaded.errors
        assert other.execute("count", entity="fact").data["count"] == 2
        # merge keeps ids; a row the table already knows by uid is an update in every mode (0.8.0)
        assert other.execute("load", path=str(out), mode="merge").data["entities"]["fact"]["updated"] == 2
        assert other.execute("count", entity="fact").data["count"] == 2
        appended = other.execute("load", path=str(out), mode="append").data["entities"]["fact"]
        assert appended == {"inserted": 0, "updated": 2, "deleted": 0, "skipped": 0}
        assert other.execute("count", entity="fact").data["count"] == 2
        # append makes new rows of a file that carries no uids (a 0.7.x dump)
        for rows in payload["entities"].values():
            for row in rows:
                del row["uid"]
        old = tmp_path / "old.json"
        old.write_text(json.dumps(payload), encoding="utf-8")
        assert other.execute("load", path=str(old), mode="append").data["entities"]["fact"]["inserted"] == 2
        assert other.execute("count", entity="fact").data["count"] == 4

    single = tmp_path / "facts.json"
    assert seeded.execute("dump", entity="fact", out=str(single)).ok
    assert json.loads(single.read_text(encoding="utf-8"))["entity"] == "fact"


def test_excel_export_and_reimport(seeded, tmp_path):
    exported = seeded.execute("export", format="excel")
    assert exported.ok, exported.errors
    path = exported.data["path"]
    wb = load_workbook(path)
    assert set(wb.sheetnames) == {
        "tasks", "facts", "WL functions", "WL use cases", "links", "JIRA", "QMS", "people", "Safety Plan",
    }
    ws = wb["Safety Plan"]
    headers = [c.value for c in ws[1]]
    assert headers[:4] == ["order", "PDP Phases", "Safety Lifecycle Phase", "Safety Deliverables"]
    assert headers.count("Tech Lead - Functional Safety") == 2 and len(headers) == 64 and headers[-1] == "uid"
    assert ws.column_dimensions["BL"].hidden and not ws.column_dimensions["BK"].hidden  # the 64th column
    assert [c.value for c in wb["facts"][1]] == ["fact order", "fact name", "fact text", "uid"]
    assert wb["facts"].column_dimensions["D"].hidden and not wb["facts"].column_dimensions["C"].hidden
    assert ws.freeze_panes == "A2"
    assert wb["links"]["D2"].hyperlink.target == "https://x.y/z"
    assert wb["tasks"]["D2"].value.date().isoformat() == "2026-10-20"

    with Brain(tmp_path / "re.db") as other:
        result = other.execute("import", format="excel", path=path, mode="replace")
        assert result.ok, result.errors
        row = other.execute("list", entity="safety_plan_row").data[0]
        assert row["deliverable"] == "Safety Plan" and row["loc_dms"] and row["reviewer_tech_lead_functional_safety"]
        assert row["author_tech_lead_functional_safety"] is False
        assert other.execute("list", entity="task").data[0]["start"] == "2026-10-20"
        # the hidden column round-trips: every row keeps the uid it had in the exporting database
        for schema in seeded.registry:
            source = {r["uid"] for r in seeded.service(schema.name).list()}
            assert {r["uid"] for r in other.service(schema.name).list()} == source


def test_locked_workbook_falls_back_to_sibling(seeded, tmp_path, monkeypatch):
    import asi_dewey.io.exporters as ex

    calls = []

    def fake_save(path):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError("locked")
        path.write_bytes(b"ok")

    path, warning = ex._save_with_fallback(fake_save, tmp_path / "view.xlsx", ".xlsx")
    assert path != tmp_path / "view.xlsx" and path.suffix == ".xlsx" and "locked" in warning


def test_run_script(seeded, tmp_path):
    script = tmp_path / "steps.jsonl"
    script.write_text(
        '# comment\n'
        '{"verb": "create", "args": {"entity": "fact", "data": {"name": "from script"}}}\n'
        '{"verb": "count", "args": {"entity": "fact"}}\n'
        '{"verb": "get", "args": {"entity": "fact", "id": 999}}\n',
        encoding="utf-8",
    )
    result = seeded.execute("run", path=str(script))
    assert not result.ok and result.data["steps"] == 3 and result.data["failed"] == [3]
    assert result.data["results"][1]["data"]["count"] == 3
    assert seeded.storage.audit_tail(3)[-1]["actor"] == "python"
    stop = seeded.execute("run", path=str(script), stop_on_error=True)
    assert stop.data["steps"] == 3


@pytest.mark.skipif(not WORKBOOK.is_file(), reason="real workbook not present")
def test_seed_from_real_workbook(tmp_path):
    with Brain(tmp_path / "seed.db") as b:
        result = b.execute("import", format="excel", path=str(WORKBOOK), mode="replace")
        assert result.ok, result.errors
        counts = b.execute("status").data["entities"]
        assert counts["task"] >= 10 and counts["safety_plan_row"] >= 48 and counts["machine_function"] >= 30
        plan = b.execute("list", entity="safety_plan_row", filter=["order=1"]).data[0]
        assert plan["lifecycle_phase"] == "1. Concept Development" and plan["ref_qf_17"] is True
        assert b.execute("list", entity="task", filter=["order=1"]).data[0]["start"] == "2026-10-19"
        out = b.execute("export", format="excel", out=str(tmp_path / "regen.xlsx"))
        assert out.ok and out.data["entities"]["safety_plan_row"] == counts["safety_plan_row"]


# -- the hidden identity in files (0.8.0, docs/hidden-identity-plan.md, 3.1) --------------------
def test_json_dump_with_shifted_ids_merges_by_uid(seeded, tmp_path):
    out = tmp_path / "dump.json"
    assert seeded.execute("dump", out=str(out)).ok
    payload = json.loads(out.read_text(encoding="utf-8"))
    before = {name: {r["uid"]: r["id"] for r in rows} for name, rows in payload["entities"].items()}
    for rows in payload["entities"].values():
        for row in rows:
            row["id"] += 100
            if "text" in row:
                row["text"] = "edited elsewhere"
    shifted = tmp_path / "shifted.json"
    shifted.write_text(json.dumps(payload), encoding="utf-8")
    result = seeded.execute("load", path=str(shifted), mode="merge")
    assert result.ok, result.errors
    assert result.data["entities"]["fact"] == {"inserted": 0, "updated": 2, "deleted": 0, "skipped": 0}
    assert sum(s["inserted"] for s in result.data["entities"].values()) == 0
    assert result.warnings == []
    facts = seeded.execute("list", entity="fact").data
    assert {r["uid"]: r["id"] for r in facts} == before["fact"]  # the rows, their ids and uids: unchanged
    assert {r["text"] for r in facts} == {"edited elsewhere"}
    # append is no different: the rows are known by uid
    assert seeded.execute("load", path=str(shifted), mode="append").data["entities"]["fact"]["inserted"] == 0
    assert seeded.execute("count", entity="fact").data["count"] == 2


def test_a_0_7_x_dump_without_uids_imports_and_the_rows_are_stamped(seeded, tmp_path):
    old = tmp_path / "old.json"
    old.write_text(json.dumps({
        "schema_version": 1, "app_version": "0.7.4", "exported_at": "2026-10-28T00:00:00+00:00",
        "entities": {
            "fact": [
                {"id": 1, "order": 1, "name": "Project code", "text": "PRJ-0002"},
                {"id": 7, "order": 3, "name": "New", "text": "fresh"},
            ],
        },
    }), encoding="utf-8")
    existing = {r["id"]: r["uid"] for r in seeded.execute("list", entity="fact").data}
    result = seeded.execute("load", path=str(old), mode="merge")
    assert result.ok and result.data["entities"]["fact"] == {"inserted": 1, "updated": 1, "deleted": 0, "skipped": 0}
    rows = {r["id"]: r for r in seeded.execute("list", entity="fact").data}
    assert rows[1]["text"] == "PRJ-0002" and rows[1]["uid"] == existing[1]  # updated by id, the uid stays
    assert rows[7]["name"] == "New" and UID_PATTERN.match(rows[7]["uid"])  # inserted with a fresh uid
    assert len({r["uid"] for r in rows.values()}) == 3
    # the same file in replace mode: every row is new, every row gets a uid
    assert seeded.execute("load", path=str(old), mode="replace").data["entities"]["fact"]["inserted"] == 2
    assert all(UID_PATTERN.match(r["uid"]) for r in seeded.execute("list", entity="fact").data)


def test_merge_by_id_keeps_the_stored_uid_and_warns(seeded, tmp_path):
    row = seeded.execute("list", entity="fact").data[0]
    foreign = new_uid()
    dump = tmp_path / "foreign.json"
    dump.write_text(json.dumps({"entity": "fact", "rows": [{"id": row["id"], "name": "renamed", "uid": foreign}]}),
                    encoding="utf-8")
    result = seeded.execute("load", path=str(dump), mode="merge")
    assert result.ok and result.data["entities"]["fact"]["updated"] == 1
    assert result.warnings == [f"fact: row 1: matched fact {row['id']} by id; its uid is kept, not {foreign}"]
    after = seeded.execute("get", entity="fact", id=row["id"]).data
    assert after["name"] == "renamed" and after["uid"] == row["uid"]


def test_a_kletz_plan_sheet_with_hidden_uids_gives_the_cached_rows_those_uids(brain, tmp_path):
    from openpyxl import Workbook

    schema = brain.registry.get("safety_plan_row")
    headers = [spec.header for spec in schema.visible_fields] + ["uid"]
    assert len(headers) == 64
    uids = [new_uid(), new_uid()]

    def sheet(path, deliverables):
        wb = Workbook()
        ws = wb.active
        ws.title = "Safety Plan"
        ws.append(headers)
        for order, (deliverable, uid) in enumerate(zip(deliverables, uids, strict=True), start=1):
            row = [None] * 64
            row[0], row[1], row[2], row[3], row[63] = order, "1", "1. Concept Development", deliverable, uid
            ws.append(row)
        ws.column_dimensions["BL"].hidden = True  # as Kletz writes it
        wb.save(path)

    first = tmp_path / "kletz.xlsx"
    sheet(first, ["Safety Plan", "HARA"])
    result = brain.execute("import", format="excel", path=str(first), mode="replace", entity="safety_plan_row")
    assert result.ok, result.errors
    assert result.data["entities"]["safety_plan_row"]["inserted"] == 2 and result.warnings == []
    rows = brain.execute("list", entity="safety_plan_row").data
    assert [r["uid"] for r in rows] == uids and [r["deliverable"] for r in rows] == ["Safety Plan", "HARA"]
    # a newer dump of the same plan updates the cached rows in place instead of duplicating them
    second = tmp_path / "kletz-later.xlsx"
    sheet(second, ["Safety Plan (rev B)", "HARA"])
    result = brain.execute("import", format="excel", path=str(second), mode="merge", entity="safety_plan_row")
    assert result.ok and result.data["entities"]["safety_plan_row"] == {
        "inserted": 0, "updated": 2, "deleted": 0, "skipped": 0,
    }
    rows = brain.execute("list", entity="safety_plan_row").data
    assert [r["uid"] for r in rows] == uids and rows[0]["deliverable"] == "Safety Plan (rev B)"
    assert brain.execute("count", entity="safety_plan_row").data["count"] == 2
