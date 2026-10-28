"""JiraService: pull Jira issues into the ``jira_ticket`` entity through asi_hopper. Read only.

Jira is the truth for tickets; the rows here are a cached view of it, the way the workbook is a
view of the database. ``sync`` upserts by issue key through the ordinary ``EntityService`` path,
so validation, the audit log (actor ``hopper``) and the event bus all apply. Nothing is ever
deleted: a row whose key is no longer returned by the JQL is reported as stale, not removed.

``live`` and ``comments`` (0.5.0) are a fetch held in memory by the caller, never written to the
database or the audit log. Their row shapes are the family convention
(``docs/jira-live-data-plan.md``, section 3.1), which asi_kletz's window still shows; Dewey's
JIRA Live Data window was removed in 0.8.1 and the verbs stay for the command line.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from ..errors import CommandError

if TYPE_CHECKING:
    from ..brain import Brain

ENTITY = "jira_ticket"
DEFAULT_JQL = "project = HWL AND (assignee = currentUser() OR watcher = currentUser()) AND statusCategory != Done"
SYNC_ACTION = "jira:sync"
STATUS_BY_CATEGORY = {"new": "open", "indeterminate": "in progress", "done": "done"}
SYNCED_FIELDS = (
    "key",
    "name",
    "status",
    "url",
    "issue_type",
    "priority",
    "assignee",
    "parent_key",
    "labels",
    "updated",
)
INSTALL_HINT = "asi_hopper is not installed: run `uv add --editable ../asi_hopper` in asi_dewey"

# the JIRA Live Data convention: shared by name with asi_kletz, never as code
# the issues that involve the person running the tool, past and present, newest first
LIVE_JQL = (
    "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser())"
    " ORDER BY updated DESC"
)
LIVE_LIMIT = 2000
LIVE_FIELDS = (
    "key",
    "issue_type",
    "summary",
    "status",
    "status_category",
    "resolution",
    "priority",
    "assignee",
    "reporter",
    "labels",
    "components",
    "parent_key",
    "created",
    "updated",
    "due",
    "url",
)


def _now() -> str:
    """UTC ISO 8601 to the second: the format the event bus stamps on ``ts``."""
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def live_row(record: Any) -> dict[str, Any]:
    """An asi_hopper ``IssueRecord`` -> the row of the JIRA Live Data convention (section 3.1).

    Lists stay lists, the type is ``issue_type`` and the parent ``parent_key`` (the ``jira_ticket``
    vocabulary), and reporter, resolution and components are kept; ``to_row`` is Hopper's CSV shape.
    """
    return {
        "key": record.key,
        "issue_type": record.issue_type,
        "summary": record.summary,
        "status": record.status,
        "status_category": record.status_category,
        "resolution": record.resolution,
        "priority": record.priority,
        "assignee": record.assignee,
        "reporter": record.reporter,
        "labels": list(record.labels),
        "components": list(record.components),
        "parent_key": record.parent.key if record.parent else None,
        "created": record.created,
        "updated": record.updated,
        "due": record.due,
        "url": record.url,
    }


def comment_row(comment: Any) -> dict[str, Any]:
    """An asi_hopper ``Comment`` -> the comments-view row: ``author_id`` dropped, body never ``None``."""
    return {
        "id": comment.id,
        "author": comment.author,
        "created": comment.created,
        "updated": comment.updated,
        "body": comment.body or "",
    }


def map_status(record: Any) -> str:
    """Jira status -> the ``jira_status`` lookup. ``blocked`` only when Jira itself says Blocked."""
    if "blocked" in (record.status or "").lower():
        return "blocked"
    return STATUS_BY_CATEGORY.get(record.status_category or "", "open")


def map_record(record: Any) -> dict[str, Any]:
    """An asi_hopper ``IssueRecord`` -> the ``jira_ticket`` columns it feeds."""
    return {
        "key": record.key,
        "name": record.summary,
        "status": map_status(record),
        "url": record.url,
        "issue_type": record.issue_type,
        "priority": record.priority,
        "assignee": record.assignee,
        "parent_key": record.parent.key if record.parent else None,
        "labels": ";".join(record.labels) or None,
        "updated": record.updated,
    }


def _same(row: dict[str, Any], data: dict[str, Any]) -> bool:
    return all((row.get(k) or None) == (v or None) for k, v in data.items())


class JiraService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- access to asi_hopper -------------------------------------------------------------
    def jql(self, override: str | None = None) -> str:
        return override or self.brain.config.get("jira_jql") or DEFAULT_JQL

    def live_jql(self, override: str | None = None) -> str:
        return override or self.brain.config.get("jira_live_jql") or LIVE_JQL

    def open_hopper(self) -> Any:
        """A read-only, non-interactive Hopper. A missing session is reported, never a browser."""
        try:
            from asi_hopper import Hopper
        except ImportError:
            raise CommandError(INSTALL_HINT) from None
        return Hopper(interactive=False)

    # -- use cases --------------------------------------------------------------------------
    def sync(
        self, jql: str | None = None, *, hopper: Any = None, dry_run: bool = False, actor: str = "hopper"
    ) -> dict[str, Any]:
        """Fetch ``jql`` and upsert the rows by key. Returns counts; with ``dry_run`` nothing is written."""
        jql = self.jql(jql)
        records = self._fetch(jql, hopper)
        service = self.brain.service(ENTITY)
        rows = service.list()
        existing = {r["key"]: r for r in rows if r.get("key")}
        next_order = max((r.get("order") or 0 for r in rows), default=0) + 1
        now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        summary: dict[str, Any] = {
            "jql": jql,
            "dry_run": dry_run,
            "fetched": len(records),
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "stale": [],
            "warnings": [],
        }
        for record in records:
            data = map_record(record)
            row = existing.get(record.key)
            if row is None:
                summary["created"] += 1
                if not dry_run:
                    _, warnings = service.create({**data, "order": next_order, "synced_at": now}, actor)
                    next_order += 1
                    summary["warnings"].extend(f"{record.key}: {w}" for w in warnings)
            elif _same(row, data):
                summary["unchanged"] += 1
            else:
                summary["updated"] += 1
                if not dry_run:
                    _, warnings = service.update(row["id"], {**data, "synced_at": now}, actor)
                    summary["warnings"].extend(f"{record.key}: {w}" for w in warnings)
        summary["stale"] = sorted(existing.keys() - {r.key for r in records})
        if not dry_run:
            counts = {k: summary[k] for k in ("fetched", "created", "updated", "unchanged")}
            self.brain.storage.audit(
                actor, SYNC_ACTION, ENTITY, None, {"jql": jql, **counts, "stale": summary["stale"]}
            )
            self.brain.events.publish("jira.synced", entity=ENTITY, actor=actor, summary=summary)
        return summary

    def get(self, key: str, *, hopper: Any = None) -> dict[str, Any]:
        """One live issue: the full asi_hopper record plus the row it would become here."""
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            record = self._guard(lambda: hopper.get(key))
        finally:
            if own:
                hopper.close()
        return {"issue": record.to_dict(), "row": map_record(record)}

    def live(self, jql: str | None = None, limit: int = LIVE_LIMIT, *, hopper: Any = None) -> dict[str, Any]:
        """Fetch ``jql`` live and return the convention's dict. Nothing is written anywhere.

        Hopper's ``limit`` returns exactly ``limit`` rows whether the query had ``limit`` or many more
        matches, so one extra row is asked for: ``truncated`` is true exactly when it arrives, and it
        is dropped. Pages are 50 issues of ``LIST_FIELDS`` only (no description, no links): a page
        of full records can exceed the MCP transport's event size limit, a page of these never does.
        """
        if limit < 1:
            raise CommandError("limit must be at least 1")
        jql = self.live_jql(jql)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            from asi_hopper import LIST_FIELDS  # lazy: ``import asi_dewey`` never loads asi_hopper

            records = self._guard(
                lambda: hopper.search(jql, fields=LIST_FIELDS, all_pages=True, limit=limit + 1, page_size=50)
            )
        finally:
            if own:
                hopper.close()
        issues = [live_row(r) for r in records[:limit]]
        return {
            "jql": jql,
            "fetched_at": _now(),
            "count": len(issues),
            "truncated": len(records) > limit,
            "issues": issues,
        }

    def comments(self, key: str, *, hopper: Any = None) -> dict[str, Any]:
        """The comment history of one issue, newest first. Nothing is written and no event is raised."""
        key = (key or "").strip().upper()
        if not key:
            raise CommandError("jira comments needs an issue key, e.g. HWL-2572")
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            record = self._guard(lambda: hopper.get(key, comments=True))
        finally:
            if own:
                hopper.close()
        items = sorted(
            (comment_row(c) for c in record.comments),
            key=lambda c: (c["created"] or "", c["id"] or ""),
            reverse=True,
        )
        return {
            "key": record.key,
            "summary": record.summary,
            "url": record.url,
            "status": record.status,
            "fetched_at": _now(),
            "count": len(items),
            "comments": items,
        }

    def status(self) -> dict[str, Any]:
        rows = self.brain.service(ENTITY).list()
        by_status: dict[str, int] = {}
        for r in rows:
            by_status[r.get("status") or ""] = by_status.get(r.get("status") or "", 0) + 1
        last = next((e for e in self.brain.storage.audit_tail(500) if e.get("action") == SYNC_ACTION), None)
        info: dict[str, Any] = {
            "jql": self.jql(),
            "rows": len(rows),
            "with_key": sum(1 for r in rows if r.get("key")),
            "by_status": by_status,
            "last_sync": {"at": last["ts"], "actor": last["actor"], **(last.get("payload") or {})} if last else None,
        }
        try:
            from asi_hopper import Hopper

            with Hopper(interactive=False) as hopper:
                st = hopper.status()
                info["hopper"] = {
                    "version": st["app_version"],
                    "gateway": st["gateway"]["name"],
                    **st.get("session", {}),
                }
        except Exception as exc:  # no asi_hopper, bad config: status still answers
            info["hopper"] = {"error": str(exc)}
        return info

    # -- helpers ----------------------------------------------------------------------------
    def _fetch(self, jql: str, hopper: Any) -> list[Any]:
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            return self._guard(lambda: hopper.search(jql))
        finally:
            if own:
                hopper.close()

    @staticmethod
    def _guard(call: Any) -> Any:
        from asi_hopper.errors import AuthRequired, HopperError

        try:
            return call()
        except AuthRequired as exc:
            raise CommandError(str(exc)) from None
        except HopperError as exc:
            raise CommandError(f"Jira read failed: {exc}") from None
