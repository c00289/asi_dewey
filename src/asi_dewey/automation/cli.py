"""CLI front end: ``asi-dewey <verb> ...``. Built from the command signatures, prints JSON.

Exit codes: 0 the command succeeded, 1 it ran and failed, 3 refused because another primary tool
holds the family slot. Since 0.7.0 a refusal in favour of a **Dewey window with a live automation
session** is forwarded to that window (``POST /execute``) and the forwarded ``Result`` is printed
untouched, exit 0 or 1 by its ``ok``: nothing marks it as forwarded, an agent learns one dialect.
A window of the other tool, a dead or absent session, or ``--no-forward`` is still exit 3.
``session`` is the one verb that opens no ``Brain`` (it must work while a window holds the lock).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..commands import CommandFactory, Result, default_command_factory
from ..version import __version__

EXIT_BUSY = 3  # another primary tool holds the slot; 1 still means "the command ran and failed"
NO_SESSION_HINT = (
    "; no automation session; the window may have been started with --no-server or ASI_DEWEY_AUTOMATION=off"
)


def _bool(text: str) -> bool:
    return text.strip().lower() in {"1", "true", "yes", "y", "on"}


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc.msg}") from None


_TYPES = {"str": str, "path": str, "int": int, "json": _json, "kv": str, "bool": _bool, "ref": str}


def build_parser(factory: CommandFactory | None = None) -> argparse.ArgumentParser:
    factory = factory or default_command_factory
    parser = argparse.ArgumentParser(
        prog="asi-dewey",
        description="ASI Dewey: FuSa working-knowledge API. Every verb prints a JSON Result.",
    )
    parser.add_argument("--db", help="SQLite file (default: $ASI_DEWEY_DB or ./dewey.db)")
    parser.add_argument("--actor", default="cli", help="Who is driving (recorded in the audit log)")
    parser.add_argument("--compact", action="store_true", help="Print single-line JSON")
    parser.add_argument(
        "--wait",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Wait up to SECONDS (polling every 250 ms) for the family slot when another primary tool "
        "is running, instead of refusing at once with exit code 3",
    )
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="Never forward a refused command to a running Dewey window's automation session: exit 3 "
        "(and --wait queues for the slot) exactly as if no session existed",
    )
    parser.add_argument("--version", action="version", version=f"asi-dewey {__version__}")
    sub = parser.add_subparsers(dest="verb", metavar="<verb>", required=True)
    for command in factory.commands():
        sp = sub.add_parser(command.verb, help=command.help, description=command.help)
        for arg in command.arguments:
            kwargs: dict[str, Any] = {"help": arg.help, "type": _TYPES.get(arg.type, str)}
            if arg.choices:
                kwargs["choices"] = list(arg.choices)
            if arg.flag:
                if arg.multiple:
                    kwargs["action"] = "append"
                elif arg.type == "bool":  # a bare --flag means true; --flag false still works
                    kwargs["nargs"] = "?"
                    kwargs["const"] = True
                kwargs["default"] = arg.default
                kwargs["required"] = arg.required
                kwargs["dest"] = arg.dest
                sp.add_argument(f"--{arg.name}", **kwargs)
            else:
                if arg.multiple:
                    kwargs["nargs"] = "+" if arg.required else "*"
                elif not arg.required:
                    kwargs["nargs"] = "?"
                    kwargs["default"] = arg.default
                sp.add_argument(arg.dest, metavar=arg.name, **kwargs)
    return parser


def _print(result: Result, compact: bool) -> None:
    text = result.to_json(indent=None if compact else 2)
    try:
        print(text)
    except UnicodeEncodeError:  # Windows consoles without UTF-8
        sys.stdout.buffer.write(text.encode("utf-8", "replace") + b"\n")


def main(argv: list[str] | None = None) -> int:
    """0: the command succeeded; 1: it ran and failed; 3: refused, another primary tool is running."""
    from ..brain import Brain
    from ..commands.session import session_report
    from ..errors import PrimaryToolBusy

    factory = default_command_factory
    parser = build_parser(factory)
    ns = parser.parse_args(argv)
    command = factory.get(ns.verb)
    args = {a.dest: getattr(ns, a.dest, None) for a in command.arguments}
    if ns.verb == "session":  # no database, no Brain, no lock: it must work while a window is open
        result = session_report(quit=bool(args.get("quit")))
        _print(result, ns.compact)
        return 0 if result.ok else 1
    try:
        brain = Brain(ns.db, wait=ns.wait)
    except PrimaryToolBusy as exc:
        result, forwarded = _forward_or_refuse(exc, ns, args)
        _print(result, ns.compact)
        if not forwarded:
            return EXIT_BUSY
        return 0 if result.ok else 1
    with brain:
        result = brain.execute(ns.verb, args, actor=ns.actor)
    _print(result, ns.compact)
    return 0 if result.ok else 1


def _forward_or_refuse(exc: Any, ns: argparse.Namespace, args: dict[str, Any]) -> tuple[Result, bool]:
    """The lock refused us: forward to a live Dewey window, or build the exit-3 refusal.

    Forward only when the holder is a window of **this tool** whose pid is the session file's,
    the session is alive (pid alive, token present) and ``GET /status`` answers with that pid.
    Returns ``(result, forwarded)``; a refusal carries ``data = {"slot", "holder"}`` and, when the
    reason is the session rather than the holder, a hint after the lock's message.
    """
    from .session import TOOL, SessionUnreachable, forward, probe, read_session

    holder = exc.holder or {}
    refusal = {"slot": exc.slot, "holder": exc.holder}
    hint = ""
    if not ns.no_forward and holder.get("tool") == TOOL:
        session = read_session()
        if session is None or holder.get("pid") != session.get("pid"):
            hint = NO_SESSION_HINT
        elif probe(session) is None:
            hint = f"; the automation session at {session['address']} did not answer"
        else:
            if ns.db is not None and _other_db(ns.db, session.get("db")):
                print(
                    f"asi-dewey: --db {ns.db} ignored: forwarded to the window's database {session.get('db')}",
                    file=sys.stderr,
                )
            try:
                return forward(session, ns.verb, args, actor=ns.actor), True
            except SessionUnreachable as sexc:
                hint = f"; {sexc}"
    return Result.failure(str(exc) + hint, data=refusal, verb=ns.verb), False


def _other_db(given: str, session_db: Any) -> bool:
    from ..locks import resolve_db

    if not session_db:
        return False
    try:
        return resolve_db(given) != resolve_db(str(session_db))
    except OSError:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
