"""The session file, pid liveness, and the CLI forwarding branch against a real window.

``main()`` blocks its thread until the forwarded answer is back, and the Tk thread is the test
thread, so every ``main`` call here runs on a helper thread while the test pumps ``window.update()``
(``run_cli``); ``capsys`` captures the thread's stdout because ``--capture=sys`` is process-wide.
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk

import pytest

from asi_dewey.automation import session as sess
from asi_dewey.automation.cli import main
from asi_dewey.errors import PrimaryToolBusy


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


HAS_TK = _tk_available()


@pytest.fixture
def finished_pid() -> int:
    """The pid of a process that has already exited."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import os; print(os.getpid())"], stdout=subprocess.PIPE, text=True
    )
    out, _ = proc.communicate(timeout=30)
    assert proc.returncode == 0
    return int(out.strip())  # the interpreter's own pid (a venv launcher's pid would be another)


# -- the file -------------------------------------------------------------------------------------
def test_session_path_is_beside_prefs(monkeypatch, tmp_path):
    from asi_dewey.prefs import prefs_path

    assert sess.session_path() == tmp_path / "session.json"  # conftest's override
    monkeypatch.delenv(sess.ENV_SESSION)
    assert sess.session_path() == prefs_path().with_name("session.json")
    assert sess.session_path().parent == prefs_path().parent


def test_read_session_none_for_missing_corrupt_other_tool_and_dead_pid(tmp_path, finished_pid):
    path = sess.session_path()
    assert not path.exists() and sess.read_session() is None and sess.read_raw_session() is None
    path.write_text("{not json", encoding="utf-8")
    assert sess.read_session() is None and sess.read_raw_session() is None
    path.write_text("[1, 2]", encoding="utf-8")
    assert sess.read_session() is None

    written = sess.write_session(51234, "a" * 32, str(tmp_path / "x.db"), "2026-10-27T17:02:11+00:00")
    assert written == path
    live = sess.read_session()
    assert live is not None and live["pid"] == os.getpid() and live["port"] == 51234 and live["token"] == "a" * 32
    assert live["address"] == "http://127.0.0.1:51234" and live["tool"] == "asi_dewey" and live["db"].endswith("x.db")
    assert set(live) == {"tool", "version", "pid", "started_at", "host", "port", "address", "token", "db"}

    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "tool": "asi_kletz"}), encoding="utf-8")
    assert sess.read_session() is None and sess.read_raw_session()["tool"] == "asi_kletz"
    path.write_text(json.dumps({**data, "pid": finished_pid}), encoding="utf-8")
    assert sess.read_session() is None
    path.write_text(json.dumps({**data, "token": ""}), encoding="utf-8")
    assert sess.read_session() is None
    path.write_text(json.dumps(data), encoding="utf-8")
    assert sess.read_session() == {**data}


def test_clear_session_only_for_its_own_pid(tmp_path):
    path = sess.write_session(1, "b" * 32, "db", "now")
    sess.clear_session(os.getpid() + 1)
    assert path.is_file()
    sess.clear_session()
    assert not path.exists()
    sess.clear_session()  # nothing there: no error


def test_pid_alive(finished_pid):
    assert sess.pid_alive(os.getpid())
    assert not sess.pid_alive(finished_pid)
    assert not sess.pid_alive(0) and not sess.pid_alive(-1) and not sess.pid_alive("12") and not sess.pid_alive(None)


def test_automation_enabled_switch(monkeypatch):
    assert sess.automation_enabled()
    monkeypatch.setenv(sess.ENV_AUTOMATION, "off")
    assert not sess.automation_enabled()
    monkeypatch.setenv(sess.ENV_AUTOMATION, "OFF ")
    assert not sess.automation_enabled()
    monkeypatch.setenv(sess.ENV_AUTOMATION, "on")
    assert sess.automation_enabled()


def test_probe_and_forward_without_a_server(tmp_path):
    import socket

    with socket.socket() as probe_socket:  # a port nobody listens on
        probe_socket.bind(("127.0.0.1", 0))
        port = probe_socket.getsockname()[1]
    session = {"pid": os.getpid(), "address": f"http://127.0.0.1:{port}", "token": "c" * 32}
    assert sess.probe(session, timeout=0.5) is None
    with pytest.raises(sess.SessionUnreachable):
        sess.forward(session, "count", {"entity": "fact"}, actor="cli", timeout=0.5)


# -- forwarding: a real window with its server, the lock refusal monkeypatched in ----------------
pytest.importorskip("asi_dewey.locks")


@pytest.fixture
def window(seeded):
    if not HAS_TK:
        pytest.skip("no display for tkinter")
    from asi_dewey.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()


@pytest.fixture
def refused(monkeypatch):
    """Make ``Brain(...)`` raise the lock refusal with the holder the test chooses."""
    import asi_dewey.brain as brain_module

    state = {"holder": {"tool": "asi_dewey", "pid": os.getpid()}}

    class Busy:
        def __init__(self, *args, **kwargs):
            raise PrimaryToolBusy("family", state["holder"])

    monkeypatch.setattr(brain_module, "Brain", Busy)

    def set_holder(**holder):
        state["holder"] = holder

    return set_holder


def run_cli(window, capsys, *argv):
    """``main(argv)`` on a helper thread while the window is pumped; ``(code, parsed stdout, stderr)``."""
    out: dict = {}

    def go():
        try:
            out["code"] = main(list(argv))
        except BaseException as exc:  # pragma: no cover
            out["error"] = exc

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while thread.is_alive() and time.time() < deadline:
        window.update()
        time.sleep(0.01)
    thread.join(timeout=1)
    if "error" in out:
        raise out["error"]
    captured = capsys.readouterr()
    return out["code"], json.loads(captured.out), captured.err


def test_same_tool_refusal_is_forwarded(window, seeded, refused, capsys):
    requests_before = window.server.requests
    code, res, err = run_cli(window, capsys, "count", "fact")
    assert code == 0
    assert res == {"ok": True, "verb": "count", "data": {"entity": "fact", "count": 2}, "errors": [], "warnings": []}
    assert err == ""
    assert window.server.requests == requests_before + 2  # the probe and the command
    code, res, err = run_cli(window, capsys, "--actor", "robot", "create", "fact", "--set", "name=remote")
    assert code == 0 and res["ok"] and res["data"]["name"] == "remote"
    assert seeded.storage.audit_tail(1)[0]["actor"] == "robot"
    code, res, err = run_cli(window, capsys, "create", "fact", "--set", "name=as-cli")
    assert code == 0 and seeded.storage.audit_tail(1)[0]["actor"] == "cli"
    code, res, err = run_cli(window, capsys, "--actor", "robot", "get", "fact", "42")
    assert code == 1 and not res["ok"] and res["verb"] == "get"


def test_other_tool_refusal_stays_exit_3(window, refused, capsys):
    refused(tool="asi_kletz", pid=4321)
    requests_before = window.server.requests
    code, res, err = run_cli(window, capsys, "count", "fact")
    assert code == 3 and not res["ok"] and res["data"]["holder"]["tool"] == "asi_kletz"
    assert res["data"]["slot"] == "family" and res["verb"] == "count"
    assert "no automation session" not in res["errors"][0]
    assert window.server.requests == requests_before


def test_wrong_pid_no_forward_and_dead_server_are_exit_3(window, refused, capsys):
    path = sess.session_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    # the holder's pid is not the session file's pid
    refused(tool="asi_dewey", pid=os.getpid() + 7)
    code, res, err = run_cli(window, capsys, "count", "fact")
    assert code == 3 and res["errors"][0].endswith(
        "no automation session; the window may have been started with --no-server or ASI_DEWEY_AUTOMATION=off"
    )
    # --no-forward with a live session
    refused(tool="asi_dewey", pid=os.getpid())
    requests_before = window.server.requests
    code, res, err = run_cli(window, capsys, "--no-forward", "count", "fact")
    assert code == 3 and not res["ok"] and res["data"]["holder"]["pid"] == os.getpid()
    assert "no automation session" not in res["errors"][0] and window.server.requests == requests_before
    # the server is gone but the file was left in place
    window.server.stop()
    window.server = None
    path.write_text(json.dumps(data), encoding="utf-8")
    code, res, err = run_cli(window, capsys, "count", "fact")
    assert code == 3 and "did not answer" in res["errors"][0] and f"http://127.0.0.1:{data['port']}" in res["errors"][0]


def test_no_session_file_is_exit_3_with_the_hint(window, refused, capsys):
    sess.session_path().unlink()
    code, res, err = run_cli(window, capsys, "count", "fact")
    assert code == 3 and "no automation session" in res["errors"][0]
    assert res["errors"][0].startswith("asi_dewey is running (pid ")


def test_db_flag_on_a_forwarded_call_warns_on_stderr(window, seeded, refused, capsys, tmp_path):
    code, res, err = run_cli(window, capsys, "--db", str(tmp_path / "other.db"), "count", "fact")
    assert code == 0 and res["data"]["count"] == 2
    assert "ignored" in err and "other.db" in err and seeded.db_path in err
    code, res, err = run_cli(window, capsys, "--db", seeded.db_path, "count", "fact")
    assert code == 0 and err == ""
