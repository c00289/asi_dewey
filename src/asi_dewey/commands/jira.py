"""The ``jira`` verb: Jira through asi_hopper, read only.

``jira sync`` pulls the configured JQL into ``jira_ticket`` (upsert by key, never delete),
``jira status`` reports the cached rows and the last sync, ``jira get <key>`` shows one live issue.
``jira live`` fetches a live table of issues (held in memory by the caller, never stored) and
publishes ``jira.live``; ``jira comments <key>`` lists one issue's comment history, newest first,
and publishes nothing. A missing Atlassian session is a ``Result.failure`` that says to run
``asi-hopper auth login``.
"""

from __future__ import annotations

from typing import Any

from ..services.jira_service import DEFAULT_JQL, LIVE_JQL, LIVE_LIMIT
from .base import Argument, Command, Context, Result
from .factory import register_command

ACTIONS = ("sync", "status", "get", "live", "comments")


@register_command
class JiraCommand(Command):
    verb = "jira"
    help = (
        "Jira through asi_hopper (read only): sync tickets into jira_ticket, status, get <key>, "
        "live (a table of issues, never stored), or comments <key>."
    )
    arguments = (
        Argument("action", " | ".join(ACTIONS), required=True, choices=ACTIONS),
        Argument("key", "Issue key for `get` and `comments`, e.g. HWL-2572"),
        Argument(
            "jql",
            f"JQL for `sync` (default: jira_jql in dewey.toml, else: {DEFAULT_JQL}); "
            f"for `live`: default jira_live_jql, else the house JQL ({LIVE_JQL})",
            flag=True,
        ),
        Argument(
            "dry-run", "For `sync`: report what would change, write nothing", flag=True, type="bool", default=False
        ),
        Argument(
            "limit", f"For `live`: most issues to fetch (default {LIVE_LIMIT})",
            flag=True, type="int", default=LIVE_LIMIT,
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        jira = ctx.brain.jira
        action = args["action"]
        if action == "status":
            return Result.success(jira.status())
        if action == "get":
            if not args.get("key"):
                return Result.failure("jira get needs an issue key, e.g. HWL-2572")
            return Result.success(jira.get(args["key"]))
        if action == "comments":
            return Result.success(jira.comments(args.get("key") or ""))
        if action == "live":
            raw = args.get("limit")
            limit = LIVE_LIMIT if raw is None else int(raw)  # `0` must reach the service, not become the default
            data = jira.live(args.get("jql"), limit)
            ctx.brain.events.publish(
                "jira.live",
                jql=data["jql"], count=data["count"], truncated=data["truncated"],
                fetched_at=data["fetched_at"], actor=ctx.actor,
            )
            warnings = []
            if data["truncated"]:
                warnings.append(f"fetch truncated at {limit} issues; narrow the JQL or raise --limit")
            return Result.success(data, warnings)
        summary = jira.sync(args.get("jql"), dry_run=bool(args.get("dry_run")), actor=ctx.actor or "hopper")
        warnings = list(summary.pop("warnings", []))
        if summary["stale"]:
            warnings.append(
                f"{len(summary['stale'])} row(s) have a key the JQL no longer returns (kept, not deleted): "
                + ", ".join(summary["stale"])
            )
        return Result.success(summary, warnings)
