"""The automation server against a real MainWindow, over urllib, with the token from the session file.

The Tk thread is the test thread, so every request runs on a helper thread while the test pumps
``window.update()`` until the answer is back (``call``); a request made without pumping is how the
504 case is produced.
"""

from __future__ import annotations

import gc
import json
import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

import pytest

from asi_dewey.automation.session import read_session, session_path
from asi_dewey.version import __version__


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        del root
        gc.collect()
        return True
    except tk.TclError:
        return False


pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for tkinter")

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@pytest.fixture
def window(seeded):
    from asi_dewey.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()


def _session() -> dict:
    data = read_session()
    assert data is not None, "no live session file"
    return data


def raw_request(address: str, method: str, path: str, body=None, token: str | None = None, headers=None, timeout=5.0):
    """One HTTP call on the calling thread: ``(status, payload)``; errors come back as HTTP statuses."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if token is not None:
        hdrs["Authorization"] = f"Bearer {token}"
    hdrs.update(headers or {})
    req = urllib.request.Request(address + path, data=data, method=method, headers=hdrs)
    try:
        with _opener.open(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def pump_until(window, done, limit: float = 10.0) -> None:
    deadline = time.time() + limit
    while not done() and time.time() < deadline:
        window.update()
        time.sleep(0.01)


def call(window, method: str, path: str, body=None, token="auto", headers=None, timeout=10.0):
    """Request on a helper thread while the test thread pumps the window; ``(status, payload)``."""
    session = _session()
    tok = session["token"] if token == "auto" else token
    out: dict = {}

    def go():
        try:
            out["answer"] = raw_request(session["address"], method, path, body, tok, headers, timeout=timeout)
        except BaseException as exc:  # pragma: no cover - surfaced below
            out["error"] = exc

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    pump_until(window, lambda: not thread.is_alive(), limit=timeout + 5)
    thread.join(timeout=1)
    if "error" in out:
        raise out["error"]
    return out["answer"]


# -- status, execute, events ---------------------------------------------------------------------
def test_status_reports_the_window(window, seeded):
    session = _session()
    assert session["tool"] == "asi_dewey" and session["pid"] == os.getpid() and len(session["token"]) == 32
    assert session["address"] == f"http://127.0.0.1:{session['port']}" and session["db"] == seeded.db_path
    assert session["version"] == __version__ and session["host"] == "127.0.0.1"
    code, res = call(window, "GET", "/status")
    assert code == 200 and res["ok"] and res["verb"] is None
    data = res["data"]
    assert data["tool"] == "asi_dewey" and data["pid"] == os.getpid() and data["db"] == seeded.db_path
    assert data["screen"] == "dashboard" and data["theme"] == {"key": "cyan-neon", "title": "Cyan Neon"}
    assert data["port"] == session["port"] == window.server.port
    assert isinstance(data["events_seq"], int) and data["events_seq"] == seeded.events.seq
    assert data["started_at"] == session["started_at"] and data["uptime_s"] >= 0 and data["requests"] >= 1
    assert data["lock"]["family"]["tool"] == "asi_dewey" and data["lock"]["family"]["pid"] == os.getpid()


def test_execute_read_verb_is_byte_equal_to_the_cli(window, seeded):
    code, res = call(window, "POST", "/execute", {"verb": "count", "args": {"entity": "fact"}, "actor": "agent"})
    assert code == 200
    expected = seeded.execute("count", entity="fact").to_json(indent=None)
    assert json.dumps(res, ensure_ascii=False, separators=(", ", ": ")) == expected
    assert res == {"ok": True, "verb": "count", "data": {"entity": "fact", "count": 2}, "errors": [], "warnings": []}


def test_execute_write_verb_refreshes_the_open_screen(window, seeded):
    screen = window.show("entity:fact")
    assert len(screen.tree.get_children()) == 2
    body = {"verb": "create", "args": {"entity": "fact", "data": {"name": "from the server"}}, "actor": "agent"}
    code, res = call(window, "POST", "/execute", body)
    assert code == 200 and res["ok"], res
    pump_until(window, lambda: len(screen.tree.get_children()) == 3, limit=2)
    assert len(screen.tree.get_children()) == 3
    assert seeded.storage.audit_tail(1)[0]["actor"] == "agent"
    last = seeded.events.last(1)[0]
    assert last["topic"] == "entity.created" and isinstance(last["seq"], int) and last["seq"] == seeded.events.seq


def test_execute_default_actor_is_agent_and_gui_is_refused(window, seeded):
    code, res = call(window, "POST", "/execute", {"verb": "create", "args": {"entity": "fact", "data": {"name": "x"}}})
    assert code == 200 and res["ok"]
    assert seeded.storage.audit_tail(1)[0]["actor"] == "agent"
    code, res = call(window, "POST", "/execute", {"verb": "gui"})
    assert code == 200 and not res["ok"] and res["errors"] == ["the window is already open"] and res["verb"] == "gui"
    code, res = call(window, "POST", "/execute", {"verb": "count", "args": [1]})
    assert code == 200 and not res["ok"] and "'args' must be an object" in res["errors"][0]
    code, res = call(window, "POST", "/execute", {"args": {}})
    assert code == 200 and not res["ok"] and "'verb'" in res["errors"][0]


def test_jobs_run_on_the_main_thread(window):
    seen: dict[str, threading.Thread] = {}

    def on_server():
        seen["handler"] = threading.current_thread()
        seen["job"] = window.server.on_main(lambda: threading.current_thread())

    thread = threading.Thread(target=on_server, daemon=True)
    thread.start()
    pump_until(window, lambda: not thread.is_alive())
    assert seen["job"] is threading.main_thread() is threading.current_thread()
    assert seen["handler"] is not threading.main_thread()


def test_events_since(window, seeded):
    for name in ("a", "b", "c"):
        seeded.execute("create", entity="fact", data={"name": name}, actor="agent")
    latest = seeded.events.seq
    code, res = call(window, "GET", "/events?since=0")
    assert code == 200 and res["ok"] and res["warnings"] == []
    seqs = [e["seq"] for e in res["data"]["events"]]
    assert res["data"]["since"] == 0 and res["data"]["seq"] == latest
    assert seqs == sorted(seqs) == list(range(1, latest + 1))
    assert all("topic" in e and "ts" in e for e in res["data"]["events"])
    code, res = call(window, "GET", f"/events?since={latest}")
    assert res["data"]["events"] == [] and res["data"]["seq"] == latest
    code, res = call(window, "GET", f"/events?since={latest - 1}")
    assert [e["seq"] for e in res["data"]["events"]] == [latest]
    code, res = call(window, "GET", "/events?since=0&limit=1")
    assert [e["seq"] for e in res["data"]["events"]] == [1]
    # history that no longer reaches back: drop the oldest events and ask from 0
    seeded.events.history.popleft()
    seeded.events.history.popleft()
    code, res = call(window, "GET", "/events?since=0")
    assert res["ok"] and res["warnings"] and "no longer in the history" in res["warnings"][0]
    assert res["data"]["events"][0]["seq"] == 3
    code, res = call(window, "GET", "/events?since=banana")
    assert code == 400 and not res["ok"]


def test_execute_resolves_a_uid_where_an_id_is_expected(window, seeded):
    row = seeded.execute("list", entity="fact").data[0]
    body = {"verb": "get", "args": {"entity": "fact", "id": row["uid"]}, "actor": "agent"}
    code, res = call(window, "POST", "/execute", body)
    assert code == 200 and res["ok"] and res["data"] == row
    body = {"verb": "update", "args": {"entity": "fact", "id": row["uid"], "set": ["text=via uid"]}}
    code, res = call(window, "POST", "/execute", body)
    assert code == 200 and res["ok"] and res["data"]["id"] == row["id"] and res["data"]["text"] == "via uid"
    body = {"verb": "delete", "args": {"entity": "fact", "id": row["uid"]}}
    code, res = call(window, "POST", "/execute", body)
    assert code == 200 and res["ok"] and res["data"] == {"entity": "fact", "deleted": row["id"]}
    code, res = call(window, "POST", "/execute", body)
    assert code == 200 and not res["ok"] and res["errors"] == [f"fact uid {row['uid']} not found"]


# -- puppeting -----------------------------------------------------------------------------------
def test_screen_and_screens(window):
    code, res = call(window, "POST", "/screen", {"show": "entity:task"})
    assert code == 200 and res["ok"] and res["data"] == {"screen": "entity:task", "title": "tasks"}
    assert window.current_key == "entity:task" and window.title().endswith("tasks")
    code, res = call(window, "GET", "/screens")
    assert code == 200 and res["ok"]
    screens = res["data"]["screens"]
    assert [s["key"] for s in screens] == [k for k, _ in window.factory.items()]
    assert [s["title"] for s in screens] == [t for _, t in window.factory.items()]
    assert [s["key"] for s in screens if s["current"]] == ["entity:task"]
    code, res = call(window, "POST", "/screen", {"show": "entity:unicorn"})
    assert code == 200 and not res["ok"] and "unknown screen" in res["errors"][0]
    assert window.current_key == "entity:task"
    code, res = call(window, "POST", "/screen", {})
    assert code == 200 and not res["ok"] and "'show'" in res["errors"][0]


def test_jira_live_is_no_longer_a_screen(window):
    from asi_dewey.errors import NotFound

    assert "jira_live" not in window.factory and "JIRA Live Data" not in [t for _, t in window.factory.items()]
    assert not hasattr(window, "jira_live") and not hasattr(window, "open_comments")
    with pytest.raises(NotFound):
        window.show("jira_live")
    code, res = call(window, "POST", "/screen", {"show": "jira_live"})
    assert code == 200 and not res["ok"] and "unknown screen" in res["errors"][0]
    assert window.current_key == "dashboard"
    code, res = call(window, "GET", "/screens")
    assert [s["key"] for s in res["data"]["screens"]][:2] == ["dashboard", "entity:task"]
    # the verb is still there for the command line and the server
    code, res = call(window, "POST", "/execute", {"verb": "jira", "args": {"action": "live"}})
    assert code == 200 and res["verb"] == "jira" and not res["ok"]  # no Hopper fixtures here: a failed Result


# -- remote recolour ------------------------------------------------------------------------------
def _prefs() -> dict:
    from asi_dewey.prefs import prefs_path

    path = prefs_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def test_remote_theme_recolours_the_window(window):
    server = window.server
    port = server.port
    code, res = call(window, "POST", "/execute", {"verb": "theme", "args": {"key": "pink-noir"}, "actor": "agent"})
    assert code == 200 and res["ok"] and res["verb"] == "theme" and res["data"]["latched"] == "pink-noir"
    assert window.theme.key == "pink-noir" and window.badge_var.get() == "PINK NOIR"
    assert window.online_var.get() == f"◉ ONLINE :{port}" and window.server is server
    assert _prefs()["theme"] == "pink-noir"
    assert window.status_text() == "Theme: Pink Noir"
    code, res = call(window, "GET", "/status")  # the pump survived the rebuild
    assert res["data"]["theme"] == {"key": "pink-noir", "title": "Pink Noir"}


def test_remote_theme_is_refused_on_a_dirty_screen_without_a_dialog(window, monkeypatch):
    screen = window.show("entity:fact")
    monkeypatch.setattr(screen, "is_dirty", lambda: True, raising=False)
    monkeypatch.setattr(window, "confirm", lambda *a, **k: pytest.fail("the server must never open a dialog"))
    code, res = call(window, "POST", "/execute", {"verb": "theme", "args": {"key": "green-day"}})
    assert code == 200 and not res["ok"] and res["verb"] == "theme"
    assert "refused" in res["errors"][0] and "entity:fact" in res["errors"][0]
    assert res["warnings"] == ["save or discard the edits, then retry"]
    assert window.theme.key == "cyan-neon" and _prefs() == {} and window.badge_var.get() == "CYAN NEON"
    # listing the catalog is not a pick: it passes even on a dirty screen
    code, res = call(window, "POST", "/execute", {"verb": "theme", "args": {"list": True}})
    assert res["ok"] and len(res["data"]["themes"]) == 32
    assert window.remote_guard("count", {"entity": "fact"}) is None


# -- transport ---------------------------------------------------------------------------------------
def test_bad_token_origin_method_body_and_path(window):
    code, res = call(window, "GET", "/status", token="0" * 32)
    assert code == 401 and not res["ok"] and res["errors"] == ["bad token"]
    code, res = call(window, "GET", "/status", token=None)
    assert code == 401 and res["errors"] == ["bad token"]
    code, res = call(window, "GET", "/status", headers={"Origin": "http://evil.example"})
    assert code == 403 and not res["ok"]
    code, res = call(window, "GET", "/execute")
    assert code == 405 and not res["ok"]
    code, res = call(window, "POST", "/execute", [1, 2])
    assert code == 400 and not res["ok"]
    code, res = call(window, "GET", "/nope")
    assert code == 404 and not res["ok"]
    code, res = call(window, "POST", "/status")
    assert code == 405


def test_timeout_answers_504_and_the_job_still_runs(window, seeded):
    window.server.timeout = 0.2
    session = _session()
    answer = raw_request(  # no window.update() while this waits: the Tk thread never gets to the job
        session["address"], "POST", "/execute",
        {"verb": "create", "args": {"entity": "fact", "data": {"name": "late"}}}, session["token"],
    )
    assert answer[0] == 504 and not answer[1]["ok"] and "did not answer" in answer[1]["errors"][0]
    assert seeded.execute("count", entity="fact").data["count"] == 2
    pump_until(window, lambda: seeded.execute("count", entity="fact").data["count"] == 3, limit=2)
    assert seeded.execute("count", entity="fact").data["count"] == 3  # it ran once the window got to it


def test_quit_closes_the_window_and_removes_the_file(window):
    path = session_path()
    port = window.server.port
    code, res = call(window, "POST", "/quit")
    assert code == 200 and res["ok"] and res["data"] == {"quit": True}
    assert path.is_file()
    pump_until(window, lambda: not path.exists(), limit=2)
    assert not path.exists() and window.server is None
    with pytest.raises(tk.TclError):
        window.winfo_exists()  # destroyed
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    window.close()  # idempotent: the fixture closes it again


def test_no_server_and_off_switch(seeded, monkeypatch):
    from asi_dewey.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False, server=False)
    win.withdraw()
    try:
        assert win.server is None and not session_path().exists() and win.online_var.get() == "◉ ONLINE"
        assert win.badge_var.get() == "CYAN NEON"
        win.about()
        assert "Automation: off" in win.status_text()
    finally:
        win.close()
        del win
        gc.collect()
    monkeypatch.setenv("ASI_DEWEY_AUTOMATION", "off")
    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    try:
        assert win.server is None and not session_path().exists() and win.online_var.get() == "◉ ONLINE"
    finally:
        win.close()
        del win
        gc.collect()


def test_close_removes_the_file_and_the_port_refuses(seeded):
    from asi_dewey.automation.server import current_server
    from asi_dewey.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    port = win.server.port
    assert current_server() is win.server and session_path().is_file()
    win.about()
    assert f"http://127.0.0.1:{port}" in win.status_text() and str(session_path()) in win.status_text()
    win.close()
    del win
    gc.collect()
    assert not session_path().exists() and current_server() is None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()


def test_a_stale_file_from_another_pid_is_left_alone(seeded):
    from asi_dewey.automation.session import clear_session
    from asi_dewey.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    path = session_path()
    try:
        stale = json.loads(path.read_text(encoding="utf-8"))
        stale["pid"] = 999999  # as if another window had overwritten the file meanwhile
        path.write_text(json.dumps(stale), encoding="utf-8")
        text = path.read_text(encoding="utf-8")
        clear_session()  # names our pid: not the file's
        clear_session(4242)
        assert path.read_text(encoding="utf-8") == text
    finally:
        win.close()
        del win
        gc.collect()
    assert path.is_file()  # close() clears only a file naming its own pid
    clear_session(999999)
    assert not path.exists()


# -- the session verb against the window in this process ------------------------------------------
def test_session_verb_reports_the_open_window(window, capsys):
    from asi_dewey.automation.cli import main

    window.show("entity:link")
    assert main(["session"]) == 0  # the window's own session: answered in-process, no request to itself
    out = capsys.readouterr().out
    res = json.loads(out)
    data = res["data"]
    assert data["present"] and data["alive"] and data["reachable"] and data["quit"] is False
    assert data["session"] == {
        "pid": os.getpid(), "port": window.server.port, "address": window.server.address,
        "started_at": window.server.started_at, "db": window.brain.db_path,
    }
    assert data["status"]["screen"] == "entity:link" and data["status"]["pid"] == os.getpid()
    assert "token" not in out and window.server.token not in out
    # the same through /execute: the verb reports the window's own session
    code, res = call(window, "POST", "/execute", {"verb": "session"})
    assert code == 200 and res["ok"] and res["verb"] == "session" and res["data"]["reachable"]
    assert window.server.token not in json.dumps(res)


def test_session_quit_closes_the_window(window, capsys):
    from asi_dewey.automation.cli import main

    path = session_path()
    assert main(["session", "--quit"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["data"]["quit"] is True
    pump_until(window, lambda: not path.exists(), limit=2)
    assert not path.exists() and window.server is None
    assert main(["session", "--quit"]) == 1
    res = json.loads(capsys.readouterr().out)
    assert not res["ok"] and res["data"]["present"] is False


def test_session_quit_over_http_from_another_process(window, seeded):
    """A real second process runs `session` and then `session --quit` against this window's server."""
    script = "from asi_dewey.automation.cli import main; import sys; raise SystemExit(main(sys.argv[1:]))"

    def run_other(*argv):
        out: dict = {}

        def go():
            out["proc"] = subprocess.run(
                [sys.executable, "-c", script, *argv], capture_output=True, text=True, env=dict(os.environ), timeout=30,
            )

        thread = threading.Thread(target=go, daemon=True)
        thread.start()
        pump_until(window, lambda: not thread.is_alive(), limit=30)
        thread.join(timeout=1)
        proc = out["proc"]
        return proc.returncode, json.loads(proc.stdout or "null"), proc.stderr

    code, res, err = run_other("session")
    assert code == 0, err
    assert res["data"]["present"] and res["data"]["alive"] and res["data"]["reachable"]
    assert res["data"]["status"]["pid"] == os.getpid() and res["data"]["session"]["port"] == window.server.port
    assert "token" not in json.dumps(res)
    path = session_path()
    code, res, err = run_other("session", "--quit")
    assert code == 0, err
    assert res["ok"] and res["data"]["quit"] is True and res["warnings"] == []
    assert not path.exists() and window.server is None
