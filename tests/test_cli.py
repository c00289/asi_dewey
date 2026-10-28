from __future__ import annotations

import json

import pytest

from asi_dewey.automation.cli import build_parser, main


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_cli_end_to_end(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    code, res = run(capsys, "--db", db, "create", "fact", "--set", "name=hello", "--set", "order=3")
    assert code == 0 and res["ok"] and res["data"]["order"] == 3

    code, res = run(
        capsys, "--db", db, "--actor", "me", "create", "task", "--data", '{"name": "t", "task_class": "status"}'
    )
    assert code == 0 and res["data"]["task_class"] == "status"

    code, res = run(capsys, "--db", db, "--compact", "list", "fact", "--filter", "order=3")
    assert code == 0 and len(res["data"]) == 1

    code, res = run(capsys, "--db", db, "get", "fact", "42")
    assert code == 1 and not res["ok"]

    code, res = run(capsys, "--db", db, "status")
    assert res["data"]["recent_audit"][0]["actor"] == "me"

    code, res = run(capsys, "--db", db, "schema", "task")
    assert res["data"]["name"] == "task"


def test_cli_rejects_bad_json(capsys, tmp_path):
    with pytest.raises(SystemExit):
        main(["--db", str(tmp_path / "x.db"), "create", "fact", "--data", "{not json"])


def test_parser_covers_every_verb():
    parser = build_parser()
    verbs = parser._subparsers._group_actions[0].choices  # type: ignore[union-attr]
    assert {"list", "get", "create", "update", "delete", "count", "schema", "status",
            "dump", "load", "export", "import", "run", "theme", "session"} <= set(verbs)


def test_theme_verb_lists_latches_and_rejects(tmp_path, capsys):
    from asi_dewey.prefs import prefs_path

    db = str(tmp_path / "cli.db")
    code, res = run(capsys, "--db", db, "theme")
    assert code == 0 and res["ok"]
    data = res["data"]
    assert len(data["themes"]) == 32 and data["latched"] is None and data["theme"] == "cyan-neon"
    assert data["default"] == "cyan-neon" and data["prefs"] == str(prefs_path())
    assert data["themes"][0] == {
        "key": "cyan-noir", "title": "Cyan Noir", "family": "cyan", "tone": "noir",
        "primary": "#12c0e2", "accent": "#ec7813",
    }
    assert [t["key"] for t in data["themes"]][12:16] == ["pink-noir", "pink-neon", "pink-dusk", "pink-day"]

    code, res = run(capsys, "--db", db, "theme", "pink-noir")
    assert code == 0 and res["data"]["latched"] == "pink-noir" and res["data"]["theme"] == "pink-noir"
    assert json.loads(prefs_path().read_text(encoding="utf-8"))["theme"] == "pink-noir"

    code, res = run(capsys, "--db", db, "theme", "--list")
    assert code == 0 and res["data"]["latched"] == "pink-noir" and len(res["data"]["themes"]) == 32

    code, res = run(capsys, "--db", db, "theme", "nope")
    assert code == 1 and not res["ok"] and "unknown theme 'nope'" in res["errors"][0]
    assert json.loads(prefs_path().read_text(encoding="utf-8"))["theme"] == "pink-noir"  # untouched


def test_theme_verb_publishes_theme_changed(brain):
    result = brain.execute("theme", key="violet-day", actor="agent")
    assert result.ok, result.errors
    last = brain.events.last(1)[0]
    assert last["topic"] == "theme.changed" and last["theme"] == "violet-day" and last["actor"] == "agent"


def test_cli_is_refused_with_exit_3_while_a_holder_runs(hold, tmp_path, capsys):
    from tests.conftest import HOLD_BRAIN

    holder = hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0")
    code, res = run(capsys, "--db", str(tmp_path / "cli.db"), "status")
    assert code == 3 and not res["ok"] and res["verb"] == "status"
    assert res["data"]["slot"] == "family" and res["data"]["holder"]["pid"] == holder.pid
    assert res["errors"][0].startswith("asi_dewey is running (pid ")
    holder.release()
    code, res = run(capsys, "--db", str(tmp_path / "cli.db"), "status")
    assert code == 0 and res["data"]["locks"]["family"]["tool"] == "asi_dewey"


def test_cli_wait_queues_for_the_slot(hold, tmp_path, capsys):
    from tests.conftest import HOLD_BRAIN

    hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0.5")
    code, res = run(capsys, "--db", str(tmp_path / "cli.db"), "--wait", "10", "count", "fact")
    assert code == 0 and res["ok"] and res["data"]["count"] == 0


def test_session_verb_without_a_window(tmp_path, capsys, monkeypatch):
    from asi_dewey.automation.session import session_path

    monkeypatch.chdir(tmp_path)  # a Brain would create ./dewey.db here; the verb must not
    code, res = run(capsys, "session")
    assert code == 0 and res["ok"] and res["verb"] is None
    assert res["data"] == {
        "path": str(session_path()), "present": False, "alive": False, "reachable": False,
        "session": None, "status": None, "quit": False,
    }
    assert not (tmp_path / "dewey.db").exists() and not list(tmp_path.glob("*.db"))
    code, res = run(capsys, "session", "--quit")
    assert code == 1 and not res["ok"] and "no live automation session" in res["errors"][0]
    assert "token" not in json.dumps(res)


def test_session_verb_is_registered_and_opens_no_brain(hold, tmp_path, capsys):
    from asi_dewey.commands import default_command_factory
    from tests.conftest import HOLD_BRAIN

    assert "session" in default_command_factory.verbs()
    assert [a.name for a in default_command_factory.get("session").arguments] == ["quit"]
    hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0")  # the lock is taken, and the verb does not care
    code, res = run(capsys, "--db", str(tmp_path / "cli.db"), "session")
    assert code == 0 and res["data"]["present"] is False
    code, res = run(capsys, "--db", str(tmp_path / "cli.db"), "status")
    assert code == 3  # a verb that needs a Brain is still refused, and no session means no forwarding
    assert res["errors"][0].endswith("--no-server or ASI_DEWEY_AUTOMATION=off")
    assert not (tmp_path / "cli.db").exists()
