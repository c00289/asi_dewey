"""The ``jira`` verb against asi_hopper's replay fixtures: no network, no session, no keyring."""

from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass

import pytest

from asi_dewey import Brain
from asi_dewey.brain import ENV_CONFIG
from asi_dewey.services.jira_service import (
    DEFAULT_JQL,
    INSTALL_HINT,
    LIVE_FIELDS,
    LIVE_JQL,
    JiraService,
    map_status,
)

from .conftest import REPO_ROOT

HOPPER_FIXTURES = REPO_ROOT.parent / "asi_hopper" / "tests" / "fixtures"
OPEN_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY status ASC, updated DESC"

pytestmark = pytest.mark.skipif(
    not (HOPPER_FIXTURES / "index.json").is_file(), reason="asi_hopper fixtures are not checked out next to asi_dewey"
)


@pytest.fixture(autouse=True)
def _replay_hopper(monkeypatch):
    """asi_hopper reads its gateway from the environment: point it at the recorded fixtures."""
    monkeypatch.delenv("ASI_HOPPER_CONFIG", raising=False)
    monkeypatch.setenv("ASI_HOPPER_GATEWAY", "replay")
    monkeypatch.setenv("ASI_HOPPER_FIXTURES", str(HOPPER_FIXTURES))


def test_sync_creates_rows_then_is_a_no_op(brain):
    first = brain.execute("jira", action="sync", jql=OPEN_JQL)
    assert first.ok, first.errors
    assert first.data["fetched"] == 3 and first.data["created"] == 3
    assert first.data["updated"] == 0 and first.data["unchanged"] == 0 and first.data["stale"] == []

    rows = brain.execute("list", entity="jira_ticket", order_by="order").data
    assert [r["key"] for r in rows] == ["HWL-2572", "HWL-2575", "HWL-2620"]
    assert [r["order"] for r in rows] == [1, 2, 3]
    peer_review, step4, bug = rows
    assert peer_review["status"] == "in progress" and peer_review["name"].startswith("STPA Step 1")
    assert peer_review["url"] == "https://asirobots.atlassian.net/browse/HWL-2572"
    assert peer_review["parent_key"] == "HWL-1915" and peer_review["issue_type"] == "Story"
    assert step4["status"] == "open" and step4["assignee"] == "Roy Mendoza - C"
    assert bug["labels"] == "VAT;e-stop;safety;test-failure" and bug["priority"] == "High"
    assert all(r["synced_at"] for r in rows)

    again = brain.execute("jira", action="sync", jql=OPEN_JQL)
    assert again.ok and again.data["unchanged"] == 3 and again.data["created"] == 0 and again.data["updated"] == 0
    actions = [e["action"] for e in brain.storage.audit_tail(10)]
    assert actions.count("jira:sync") == 2 and actions[-1] == "create"
    assert brain.storage.audit_tail(1)[0]["actor"] == "python"


def test_sync_updates_changed_rows_and_reports_stale_ones(brain):
    brain.execute("create", entity="jira_ticket", data={"order": 9, "key": "HWL-2572", "name": "old", "status": "done"})
    brain.execute("create", entity="jira_ticket", data={"order": 8, "key": "HWL-1", "name": "gone", "status": "open"})
    brain.execute("create", entity="jira_ticket", data={"order": 7, "name": "typed by hand", "status": "open"})
    r = brain.execute("jira", action="sync", jql=OPEN_JQL, actor="agent")
    assert r.ok, r.errors
    assert r.data["updated"] == 1 and r.data["created"] == 2 and r.data["stale"] == ["HWL-1"]
    assert r.warnings and "HWL-1" in r.warnings[0] and "not deleted" in r.warnings[0]
    rows = {r.get("key"): r for r in brain.execute("list", entity="jira_ticket").data}
    assert rows["HWL-2572"]["status"] == "in progress" and rows["HWL-2572"]["name"].startswith("STPA")
    assert rows["HWL-2572"]["order"] == 9  # order is the engineer's, sync does not touch it
    assert rows["HWL-1"]["name"] == "gone" and rows[None]["name"] == "typed by hand"
    assert max(r["order"] for r in rows.values()) == 11  # new rows go after the existing ones
    tail = brain.storage.audit_tail(1)[0]
    assert tail["action"] == "jira:sync" and tail["actor"] == "agent" and tail["payload"]["stale"] == ["HWL-1"]


def test_dry_run_writes_nothing(brain):
    r = brain.execute("jira", action="sync", jql=OPEN_JQL, dry_run=True)
    assert r.ok and r.data["dry_run"] and r.data["created"] == 3
    assert brain.execute("count", entity="jira_ticket").data["count"] == 0
    assert all(e["action"] != "jira:sync" for e in brain.storage.audit_tail(10))


def test_status_and_get(brain):
    before = brain.execute("jira", action="status")
    assert before.ok and before.data["rows"] == 0 and before.data["last_sync"] is None
    assert before.data["jql"] == DEFAULT_JQL
    assert before.data["hopper"]["version"] and before.data["hopper"]["gateway"] == "replay"
    brain.execute("jira", action="sync", jql=OPEN_JQL)
    after = brain.execute("jira", action="status")
    assert after.data["rows"] == 3 and after.data["with_key"] == 3
    assert after.data["by_status"] == {"in progress": 1, "open": 2}
    assert after.data["last_sync"]["fetched"] == 3 and after.data["last_sync"]["jql"] == OPEN_JQL

    got = brain.execute("jira", action="get", key="HWL-2575")
    assert got.ok, got.errors
    assert got.data["issue"]["key"] == "HWL-2575" and got.data["issue"]["links"][0]["other"]["key"] == "HWL-2574"
    assert got.data["row"] == {
        "key": "HWL-2575",
        "name": "STPA Step 4 – Loss Scenarios – Work",
        "status": "open",
        "url": "https://asirobots.atlassian.net/browse/HWL-2575",
        "issue_type": "Story",
        "priority": "Un-Groomed",
        "assignee": "Roy Mendoza - C",
        "parent_key": "HWL-1915",
        "labels": None,
        "updated": "2026-10-27T11:18:59.416-0600",
    }
    assert not brain.execute("jira", action="get").ok
    unrecorded = brain.execute("jira", action="get", key="HWL-1")
    assert not unrecorded.ok and "Jira read failed" in unrecorded.errors[0]
    assert not brain.execute("jira", action="dance").ok


def test_status_mapping():
    class R:
        def __init__(self, status, category):
            self.status, self.status_category = status, category

    assert map_status(R("To Do", "new")) == "open"
    assert map_status(R("In Review", "indeterminate")) == "in progress"
    assert map_status(R("Done", "done")) == "done"
    assert map_status(R("Development - Blocked", "indeterminate")) == "blocked"
    assert map_status(R("Blocked", "new")) == "blocked"
    assert map_status(R(None, None)) == "open"


def test_excel_round_trip_keeps_the_new_columns(brain, tmp_path):
    brain.execute("jira", action="sync", jql=OPEN_JQL)
    out = tmp_path / "view.xlsx"
    assert brain.execute("export", format="excel", out=str(out)).ok
    brain.execute("delete", entity="jira_ticket", id=1)
    imported = brain.execute("import", format="excel", path=str(out), mode="replace")
    assert imported.ok, imported.errors
    rows = brain.execute("list", entity="jira_ticket", order_by="order").data
    assert [r["key"] for r in rows] == ["HWL-2572", "HWL-2575", "HWL-2620"]
    assert rows[2]["labels"] == "VAT;e-stop;safety;test-failure"


# -- jira live: the JIRA Live Data fetch (0.5.0) ------------------------------------------
def _aware_utc(stamp: str) -> bool:
    parsed = dt.datetime.fromisoformat(stamp)
    return parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0)


def test_live_on_replay_writes_nothing_and_publishes(brain):
    audit_before = brain.storage.audit_tail(10)
    r = brain.execute("jira", action="live", jql=OPEN_JQL)
    assert r.ok, r.errors
    data = r.data
    assert data["count"] == 3 and data["truncated"] is False and data["jql"] == OPEN_JQL and r.warnings == []
    assert [i["key"] for i in data["issues"]] == ["HWL-2572", "HWL-2575", "HWL-2620"]
    assert _aware_utc(data["fetched_at"])
    for row in data["issues"]:
        assert tuple(row) == LIVE_FIELDS
        assert isinstance(row["labels"], list) and isinstance(row["components"], list)
    peer_review, _, bug = data["issues"]
    assert peer_review["parent_key"] == "HWL-1915" and peer_review["status_category"] == "indeterminate"
    assert peer_review["issue_type"] == "Story" and peer_review["reporter"]
    assert bug["labels"] == ["VAT", "e-stop", "safety", "test-failure"]
    # nothing written: the event is the trace
    assert brain.execute("count", entity="jira_ticket").data["count"] == 0
    assert brain.storage.audit_tail(10) == audit_before
    event = brain.events.last(1)[0]
    assert {k: event[k] for k in ("topic", "count", "truncated", "jql", "actor")} == {
        "topic": "jira.live", "count": 3, "truncated": False, "jql": OPEN_JQL, "actor": "python",
    }
    assert event["fetched_at"] == data["fetched_at"]


def test_live_limit_probe_and_truncation(brain):
    two = brain.execute("jira", action="live", jql=OPEN_JQL, limit=2)
    assert two.ok and two.data["count"] == 2 and two.data["truncated"] is True
    assert [i["key"] for i in two.data["issues"]] == ["HWL-2572", "HWL-2575"]
    assert "truncated at 2" in two.warnings[0]
    three = brain.execute("jira", action="live", jql=OPEN_JQL, limit=3)
    assert three.ok and three.data["count"] == 3 and three.data["truncated"] is False and three.warnings == []
    zero = brain.execute("jira", action="live", jql=OPEN_JQL, limit=0)
    assert not zero.ok and "limit" in zero.errors[0]


def test_live_house_jql_is_unrecorded(brain):
    assert brain.jira.live_jql() == LIVE_JQL
    r = brain.execute("jira", action="live")
    assert not r.ok and r.errors[0].startswith("Jira read failed:")
    assert brain.execute("count", entity="jira_ticket").data["count"] == 0


def test_live_jql_from_config(tmp_path, monkeypatch):
    config = tmp_path / "dewey.toml"
    config.write_text(f'jira_live_jql = "{OPEN_JQL}"\n', encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "cfg.db") as b:
        assert b.jira.live_jql() == OPEN_JQL
        r = b.execute("jira", action="live")
        assert r.ok, r.errors
        assert r.data["count"] == 3 and r.data["jql"] == OPEN_JQL


@dataclass(frozen=True)
class FakeRef:
    key: str


@dataclass(frozen=True)
class FakeComment:
    id: str | None
    author: str | None
    author_id: str | None
    created: str | None
    updated: str | None
    body: str | None


@dataclass(frozen=True)
class FakeIssue:
    """The attributes ``live_row`` and ``comments`` read, nothing else."""

    key: str
    summary: str = ""
    issue_type: str | None = None
    status: str | None = None
    status_category: str | None = None
    resolution: str | None = None
    priority: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    labels: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    parent: FakeRef | None = None
    created: str | None = None
    updated: str | None = None
    due: str | None = None
    url: str = ""
    comments: tuple[FakeComment, ...] = ()


class StubHopper:
    def __init__(self, records=(), error: Exception | None = None) -> None:
        self.records = list(records)
        self.error = error
        self.calls: list[tuple] = []
        self.closed = 0

    def search(self, jql, *, fields=None, all_pages, limit, page_size=50):
        assert fields is not None and "description" not in fields and "summary" in fields  # list fields only
        assert page_size == 50
        self.calls.append(("search", jql, all_pages, limit))
        if self.error:
            raise self.error
        return self.records[:limit]

    def get(self, key, *, comments=False):
        self.calls.append(("get", key, comments))
        if self.error:
            raise self.error
        return self.records[0]

    def close(self) -> None:
        self.closed += 1


def test_live_service_with_a_stub(brain, monkeypatch):
    issues = [FakeIssue(f"HWL-{n}", summary=f"issue {n}", parent=FakeRef("HWL-1")) for n in range(1, 7)]
    stub = StubHopper(issues)
    monkeypatch.setattr(brain.jira, "open_hopper", lambda: stub)
    data = brain.jira.live(limit=5)
    assert stub.calls == [("search", LIVE_JQL, True, 6)]
    assert data["count"] == 5 and data["truncated"] is True and stub.closed == 1
    assert data["issues"][0]["parent_key"] == "HWL-1"

    exact = StubHopper(issues[:5])
    data = brain.jira.live("project = X", 5, hopper=exact)
    assert exact.calls == [("search", "project = X", True, 6)]
    assert data["count"] == 5 and data["truncated"] is False and exact.closed == 0  # passed in: not closed

    bare = StubHopper([FakeIssue("X-1")])
    row = brain.jira.live(hopper=bare)["issues"][0]
    assert row["labels"] == [] and row["components"] == [] and row["parent_key"] is None
    assert all(row[k] is None for k in LIVE_FIELDS if k not in ("key", "summary", "labels", "components", "url"))


def test_live_failures_come_back_as_results(brain, monkeypatch):
    from asi_hopper.errors import AuthRequired

    stub = StubHopper(error=AuthRequired("no Atlassian session for this account; run `asi-hopper auth login` once"))
    monkeypatch.setattr(brain.jira, "open_hopper", lambda: stub)
    r = brain.execute("jira", action="live")
    assert not r.ok and "asi-hopper auth login" in r.errors[0] and stub.closed == 1

    monkeypatch.setattr(brain.jira, "open_hopper", JiraService.open_hopper.__get__(brain.jira))
    monkeypatch.setitem(sys.modules, "asi_hopper", None)  # `from asi_hopper import Hopper` -> ImportError
    r = brain.execute("jira", action="live")
    assert not r.ok and r.errors[0] == INSTALL_HINT


def test_jira_schema_lists_the_new_actions(brain):
    assert not brain.execute("jira", action="dance").ok
    commands = brain.execute("schema").data["commands"]
    sig = commands["jira"] if isinstance(commands, dict) else next(c for c in commands if c["verb"] == "jira")
    args = {a["name"]: a for a in sig["arguments"]}
    assert set(args["action"]["choices"]) >= {"live", "comments"}
    assert args["limit"]["type"] == "int" and args["limit"]["default"] == 2000 and args["limit"]["flag"]


# -- jira comments: the comments view's verb (0.5.0) ----------------------------------------
def test_comments_on_replay(brain):
    audit_before = brain.storage.audit_tail(10)
    events_before = brain.events.last(1)
    r = brain.execute("jira", action="comments", key="HWL-2575")
    assert r.ok, r.errors
    assert r.data["key"] == "HWL-2575" and r.data["summary"].startswith("STPA Step 4")
    assert r.data["url"].endswith("/browse/HWL-2575") and r.data["status"]
    assert r.data["count"] == 0 and r.data["comments"] == [] and _aware_utc(r.data["fetched_at"])
    lower = brain.execute("jira", action="comments", key="hwl-2575")
    assert lower.ok and lower.data["key"] == "HWL-2575"
    unknown = brain.execute("jira", action="comments", key="HWL-1")
    assert not unknown.ok and unknown.errors[0].startswith("Jira read failed:")
    missing = brain.execute("jira", action="comments")
    assert not missing.ok and "key" in missing.errors[0]
    assert brain.events.last(1) == events_before  # no event
    assert brain.storage.audit_tail(10) == audit_before
    assert brain.execute("count", entity="jira_ticket").data["count"] == 0


def test_comments_service_orders_newest_first(brain, monkeypatch):
    from asi_hopper.errors import AuthRequired

    history = (
        FakeComment("c1", "Ada", "a1", "2026-10-01T09:00:00.000-0600", "2026-10-01T09:00:00.000-0600", "first"),
        FakeComment("c3", "Bob", "b1", "2026-10-03T09:00:00.000-0600", "2026-10-03T10:30:00.000-0600", "third"),
        FakeComment("c2", "Cy", "c1", "2026-10-02T09:00:00.000-0600", "2026-10-02T09:00:00.000-0600", None),
    )
    stub = StubHopper([FakeIssue("HWL-9", summary="s", status="Done", url="u", comments=history)])
    monkeypatch.setattr(brain.jira, "open_hopper", lambda: stub)
    data = brain.jira.comments("hwl-9")
    assert stub.calls == [("get", "HWL-9", True)] and stub.closed == 1
    assert [c["id"] for c in data["comments"]] == ["c3", "c2", "c1"] and data["count"] == 3
    assert data["comments"][0]["updated"] == "2026-10-03T10:30:00.000-0600"
    assert data["comments"][1]["body"] == "" and "author_id" not in data["comments"][0]
    assert data["comments"][0]["author"] == "Bob"

    stub.error = AuthRequired("no Atlassian session for this account; run `asi-hopper auth login` once")
    r = brain.execute("jira", action="comments", key="HWL-9")
    assert not r.ok and "asi-hopper auth login" in r.errors[0]


def test_replay_end_to_end_as_the_windows_send_it(brain):
    live = brain.execute("jira", action="live", jql=OPEN_JQL, actor="gui")
    assert live.ok and live.data["count"] == 3 and brain.events.last(1)[0]["actor"] == "gui"
    comments = brain.execute("jira", action="comments", key="HWL-2575", actor="gui")
    assert comments.ok and comments.data["comments"] == []
