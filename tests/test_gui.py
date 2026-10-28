from __future__ import annotations

import gc
import threading
import time
import tkinter as tk
from tkinter import ttk

import pytest

from asi_dewey.commands import default_command_factory
from asi_dewey.schema import FieldType


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        del root
        gc.collect()  # delete the Tcl interpreter now, not while the next one is initialising
        return True
    except tk.TclError:
        return False


pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for tkinter")


@pytest.fixture
def window(seeded):
    from asi_dewey.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()  # same reason: a lingering interpreter torn down mid-startup breaks the next Tk()


def test_navigation_and_dashboard(window):
    keys = [k for k, _ in window.factory.items()]
    assert keys == [
        "dashboard", "jira_live", "entity:task", "entity:fact", "entity:machine_function", "entity:use_case",
        "entity:link", "entity:qms_document", "entity:person", "transfer", "generate",
    ]
    assert window.current.key == "dashboard"
    dash = window.current
    assert dash._tile_vars["fact"].get() == "2"
    window.show("entity:fact")
    assert window.current_key == "entity:fact" and window.title().endswith("facts")


def test_entity_screen_create_update_delete(window, seeded):
    screen = window.show("entity:fact")
    assert len(screen.tree.get_children()) == 2
    screen.new()
    screen.widgets["name"].set("GUI fact")
    screen.widgets["order"].set("9")
    screen.widgets["text"].set("line one\nline two")
    screen.save()
    assert screen.selected_id is not None
    assert seeded.execute("count", entity="fact").data["count"] == 3
    row = seeded.execute("get", entity="fact", id=screen.selected_id).data
    assert row["order"] == 9 and row["text"] == "line one\nline two"

    screen.widgets["text"].set("edited")
    screen.save()
    assert seeded.execute("get", entity="fact", id=screen.selected_id).data["text"] == "edited"
    assert seeded.storage.audit_tail(1)[0]["actor"] == "gui"

    screen.delete()
    assert seeded.execute("count", entity="fact").data["count"] == 2
    assert screen.selected_id is None and "Deleted" in window.status_text()


def test_entity_screen_validation_shows_error(window, seeded):
    screen = window.show("entity:task")
    screen.new()
    screen.widgets["start"].set("banana")
    screen.save()
    assert window.status_text().startswith("Error:") and "required" in window.status_text()
    assert seeded.execute("count", entity="task").data["count"] == 1


def test_search_sort_and_select(window):
    screen = window.show("entity:fact")
    screen.search_var.set("product")
    assert len(screen.tree.get_children()) == 1
    screen.search_var.set("")
    screen.sort_by("order", desc=True)
    first = int(screen.tree.get_children()[0])
    assert screen.by_id[first]["order"] == 2
    screen.select(first)
    assert screen.widgets["name"].get() == "Product"
    screen.duplicate()
    assert screen.selected_id is None and screen.widgets["order"].get() is None


def test_pruned_screens_are_absent(window, seeded):
    from asi_dewey.errors import NotFound
    from asi_dewey.gui.screens import HIDDEN_ENTITY_SCREENS

    assert HIDDEN_ENTITY_SCREENS == frozenset({"jira_ticket", "safety_plan_row"})
    keys = [k for k, _ in window.factory.items()]
    for key in ("entity:jira_ticket", "entity:safety_plan_row", "safety_plan_matrix"):
        assert key not in keys and key not in window.factory
    assert len(keys) == 11  # ten after the prune, plus JIRA Live Data (0.5.0)
    with pytest.raises(NotFound):
        window.show("safety_plan_matrix")
    with pytest.raises(NotFound):
        window.show("entity:jira_ticket")
    assert window.current_key == "dashboard"
    # the View menu lists exactly the factory's titles, then the Theme cascade
    menubar = window.nametowidget(window.cget("menu"))
    tops = [i for i in range(menubar.index("end") + 1) if menubar.type(i) == "cascade"]
    assert menubar.entrycget(tops[1], "label") == "View"
    view_menu = window.nametowidget(menubar.entrycget(tops[1], "menu"))
    labels = [view_menu.entrycget(i, "label") for i in range(view_menu.index("end") + 1)
              if view_menu.type(i) == "command"]
    assert labels == [t for _, t in window.factory.items()]
    assert not {"JIRA", "Safety Plan", "Safety Plan Matrix"} & set(labels)
    last = view_menu.index("end")
    assert view_menu.type(last) == "cascade" and view_menu.entrycget(last, "label") == "Theme"
    # the navigation list follows the factory too
    assert window.nav.size() == 11
    rows = [row.strip() for row in window.nav.get(0, "end")]
    assert "JIRA" not in rows and not any(row.startswith("SAFETY PLAN") for row in rows)
    # the entities stay: tables, commands and counts are untouched
    assert "jira_ticket" in seeded.registry and "safety_plan_row" in seeded.registry
    assert len(seeded.registry) == 9
    assert seeded.execute("count", entity="safety_plan_row").data["count"] == 1
    # the dashboard still counts both; the Safety Plan tile is not clickable, the Jira one opens the live view
    dash = window.current
    assert dash._tile_vars["safety_plan_row"].get() == "1" and dash._tile_vars["jira_ticket"].get() == "0"
    names = list(dash._tile_vars)
    tiles = dash.tiles.winfo_children()
    assert tiles[names.index("safety_plan_row")].bind("<Button-1>") == ""
    assert tiles[names.index("jira_ticket")].bind("<Button-1>") != ""  # TILE_TARGETS: jira_live (0.5.0)
    assert tiles[names.index("fact")].bind("<Button-1>") != ""


def test_hidden_set_must_name_registered_entities(seeded):
    from asi_dewey.gui.screens import build_default_screens

    with pytest.raises(ValueError):
        build_default_screens(seeded, hidden=frozenset({"unicorn"}))
    keys = [k for k, _ in build_default_screens(seeded, hidden=frozenset()).items()]
    assert len(keys) == 13 and "entity:jira_ticket" in keys and "entity:safety_plan_row" in keys


def test_event_bus_refreshes_open_screen(window, seeded):
    screen = window.show("entity:fact")
    seeded.execute("create", entity="fact", data={"name": "from the API"}, actor="agent")
    deadline = time.time() + 2
    while len(screen.tree.get_children()) < 3 and time.time() < deadline:
        window.update()
        time.sleep(0.02)
    assert len(screen.tree.get_children()) == 3


def test_transfer_screen_round_trip(window, tmp_path, seeded):
    screen = window.show("transfer")
    exported = screen.export_workbook(tmp_path / "view.xlsx")
    assert exported.ok and (tmp_path / "view.xlsx").is_file()
    dumped = screen.dump_json(tmp_path / "dump.json")
    assert dumped.ok
    assert screen.load_json(tmp_path / "dump.json", mode="merge").ok
    assert screen.import_workbook(tmp_path / "view.xlsx", mode="replace").ok
    assert seeded.execute("count", entity="fact").data["count"] == 2
    assert "[ok] import" in screen.log.get("1.0", "end")
    assert not screen.dump_json().ok  # no dialog when not interactive


def test_widget_factory_round_trips(window, seeded):
    from asi_dewey.gui.widgets import WidgetFactory

    factory = WidgetFactory(seeded.lookups)
    task = seeded.registry.get("task")
    plan = seeded.registry.get("safety_plan_row")
    samples = {
        "name": ("hello", "hello"), "start": ("2026-01-02", "2026-01-02"),
        "comments": ("a\nb", "a\nb"), "order": ("5", "5"), "task_class": ("status", "status"),
    }
    for field, (given, expected) in samples.items():
        widget = factory.create(window, task.field(field))
        widget.set(given)
        assert widget.get() == expected
        widget.clear()
        assert widget.get() is None
    flag = factory.create(window, plan.field("loc_dms"))
    flag.set(1)
    assert flag.get() is True
    url = factory.create(window, seeded.registry.get("link").field("url"))
    url.set("https://example.invalid")
    assert url.get() == "https://example.invalid"
    enum = factory.create(window, task.field("task_class"))
    assert list(enum.combo["values"]) == list(seeded.lookups["task_class"])
    assert task.field("task_class").type is FieldType.ENUM


def test_gui_verb_is_registered():
    assert "gui" in default_command_factory.verbs()


def test_cyan_neon_is_default_and_paints_ttk(window):
    from tkinter import ttk

    from asi_dewey.gui.theme import ThemeFactory, TronTheme

    assert window.theme.key == "cyan-neon" and isinstance(window.theme, TronTheme)  # tron is an alias
    style = ttk.Style(window)
    assert style.theme_use() == "clam"
    assert style.lookup("TButton", "foreground") == window.theme.palette.primary
    assert style.lookup("Treeview.Heading", "background") == window.theme.palette.panel
    assert window.nav.option_get("background", "Listbox") == window.theme.palette.panel
    assert set(ThemeFactory.keys()) >= {"tron", "plain", "cyan-neon", "pink-noir"}
    screen = window.show("entity:fact")
    first = screen.tree.get_children()[0]
    assert screen.tree.item(first, "tags") == ("even",)


def test_plain_theme_and_unknown_theme(seeded):
    import gc

    from asi_dewey.errors import NotFound
    from asi_dewey.gui.main_window import MainWindow
    from asi_dewey.gui.theme import ThemeFactory

    with pytest.raises(NotFound):
        ThemeFactory.create("neon-pink")
    win = MainWindow(seeded, interactive=False, theme="plain")
    win.withdraw()
    try:
        assert win.theme.key == "plain"
        assert win.show("dashboard").key == "dashboard"
    finally:
        win.close()
        del win
        gc.collect()


def test_gui_verb_accepts_theme():
    command = default_command_factory.get("gui")
    assert [a.name for a in command.arguments] == ["theme", "no-server"]


def test_generate_screen_builds_through_the_verbs(window, seeded, tmp_path):
    assert "generate" in [k for k, _ in window.factory.items()]
    screen = window.show("generate")
    assert [s["key"] for s in screen.catalog["diagram"]] == [
        "schema_map", "lifecycle_overview", "phase_flow", "task_flow",
    ]
    assert [s["key"] for s in screen.catalog["document"]] == ["safety_plan", "status_report", "handbook"]
    assert str(screen.open_file_button["state"]) == "disabled" and str(screen.open_folder_button["state"]) == "disabled"
    assert not screen.build_selected().ok  # nothing selected

    screen.out_var.set(str(tmp_path / "gen"))
    screen.select("diagram", "schema_map")
    assert screen.lists["diagram"].curselection() == (0,)
    assert "No parameters" in str(screen.params_inner.winfo_children()[0].cget("text"))
    result = screen.build_selected()
    assert result.ok, result.errors
    log = screen.log.get("1.0", "end")
    assert "[ok] diagram schema_map" in log and (tmp_path / "gen" / "schema_map.png").is_file()
    assert str(screen.open_file_button["state"]) == "normal" and screen.last_primary.endswith("schema_map.png")
    assert seeded.storage.audit_tail(1)[0]["actor"] == "gui"

    screen.select("diagram", "phase_flow")
    assert list(screen.param_vars) == ["phase"]
    failed = screen.build_selected()
    assert not failed.ok and "[failed] diagram phase_flow" in screen.log.get("1.0", "end")
    assert window.status_text().startswith("Error:")
    combo = next(w for w in screen.params_inner.winfo_children() if isinstance(w, ttk.Combobox))
    assert list(combo["values"]) == list(seeded.lookups["lifecycle_phase"])
    screen.param_vars["phase"].set("1")
    assert screen.build_selected().ok

    screen.select("document", "handbook")
    assert screen.lists["diagram"].curselection() == () and screen.lists["document"].curselection() == (2,)
    result = screen.build_selected()
    assert result.ok, result.errors
    assert "[ok] document handbook" in screen.log.get("1.0", "end") and screen.last_primary.endswith("handbook.pdf")
    assert "pages" in window.status_text()
    screen.open_file()  # not interactive: logs the path instead of launching a viewer
    screen.open_folder()
    log = screen.log.get("1.0", "end")
    assert f"open: {screen.last_primary}" in log and f"open: {tmp_path / 'gen'}" in log


def test_file_menu_build_document_focuses_documents(window):
    screen = window.build_document()
    assert window.current_key == "generate" and screen.selected == ("document", "safety_plan")
    assert screen.lists["document"].curselection() == (0,)


# -- theme picker and live repaint ------------------------------------------
PLAIN_TITLE = "Plain (native)"


def _prefs() -> dict:
    import json
    from pathlib import Path

    from asi_dewey.prefs import prefs_path

    path = Path(prefs_path())
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _open(seeded, **kwargs):
    from asi_dewey.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False, **kwargs)
    win.withdraw()
    return win


def _shut(win) -> None:
    win.close()
    del win
    gc.collect()


def test_theme_picker_lists_the_catalog_then_plain(window):
    from asi_dewey.gui.palettes import CATALOG

    assert window.theme_var.get() == "Cyan Neon"
    assert str(window.theme_box.cget("state")) == "readonly"
    assert list(window.theme_box.cget("values")) == [e.title for e in CATALOG.values()] + [PLAIN_TITLE]
    assert window.theme_box.get() == "Cyan Neon"


def test_pick_theme_repaints_and_latches(window):
    window.show("entity:fact")
    nav_before = window.nav
    result = window.pick_theme("pink-noir")
    assert result.ok, result.errors
    assert window.theme.key == "pink-noir" and window.theme_var.get() == "Pink Noir"
    style = ttk.Style(window)
    assert style.theme_use() == "clam"
    assert style.lookup("TButton", "foreground") == "#ec1380" == window.theme.palette.primary
    assert _prefs()["theme"] == "pink-noir"
    assert window.current_key == "entity:fact" and window.current.key == "entity:fact"
    assert window.status_text() == "Theme: Pink Noir"
    assert window.nav is not nav_before and window.nav.cget("background") == window.theme.palette.panel
    assert window.nav.option_get("background", "Listbox") == window.theme.palette.panel
    # every screen survives a rebuild: the cache is empty and each one can be created again
    assert window._screens.keys() == {"entity:fact"}
    for key, _ in window.factory.items():
        assert window.show(key).key == key
    # the picker itself drives the same path
    window.theme_var.set("Gold Noir")
    window._on_theme_pick(None)
    assert window.theme.key == "gold-noir" and _prefs()["theme"] == "gold-noir"


def test_pick_plain_then_back_to_a_grid_palette(window):
    from asi_dewey.gui.theme import platform_defaults

    platform = platform_defaults(window)["ttk_theme"]
    assert platform != "clam"
    assert window.pick_theme("plain").ok
    style = ttk.Style(window)
    assert window.theme.key == "plain" and style.theme_use() == platform
    assert window.nav.option_get("background", "Listbox") == "" and not window.nav.cget("background").startswith("#")
    assert window.theme_var.get() == PLAIN_TITLE and window.status_text() == f"Theme: {PLAIN_TITLE}"
    assert _prefs()["theme"] == "plain"
    assert window.show("dashboard").key == "dashboard"

    assert window.pick_theme("gold-day").ok
    style = ttk.Style(window)
    assert window.theme.key == "gold-day" and style.theme_use() == "clam"
    assert style.lookup("Treeview", "foreground", ["selected"]) == window.theme.palette.text
    assert style.lookup("TButton", "foreground") == window.theme.palette.primary
    assert window.nav.option_get("background", "Listbox") == window.theme.palette.panel


def test_pick_unknown_theme_leaves_window_and_resyncs_picker(window):
    window.theme_var.set("Nothing Here")
    result = window.pick_theme("sepia")
    assert not result.ok and window.theme.key == "cyan-neon" and window.theme_var.get() == "Cyan Neon"
    assert window.status_text().startswith("Error:") and _prefs() == {}


def test_pick_theme_asks_when_the_screen_is_dirty(window, monkeypatch):
    screen = window.show("entity:fact")
    monkeypatch.setattr(screen, "is_dirty", lambda: True, raising=False)
    monkeypatch.setattr(window, "confirm", lambda title, message: False)
    window.theme_var.set("Red Neon")
    assert not window.pick_theme("red-neon").ok
    assert window.theme.key == "cyan-neon" and window.theme_var.get() == "Cyan Neon" and _prefs() == {}
    monkeypatch.setattr(window, "confirm", lambda title, message: True)
    assert window.pick_theme("red-neon").ok and window.theme.key == "red-neon"


def test_latched_theme_opens_the_window(seeded):
    from asi_dewey.prefs import write_prefs

    write_prefs(theme="violet-dusk")
    before = _prefs()
    win = _open(seeded)
    try:
        assert win.theme.key == "violet-dusk" and win.theme_var.get() == "Violet Dusk"
        assert ttk.Style(win).lookup("TButton", "foreground") == win.theme.palette.primary
    finally:
        _shut(win)
    win = _open(seeded, theme="plain")  # a one-off override: visible in the picker, never latched
    try:
        assert win.theme.key == "plain" and win.theme_var.get() == PLAIN_TITLE
        assert _prefs() == before
    finally:
        _shut(win)


def test_unknown_latched_key_falls_back_and_warns(seeded):
    from asi_dewey.prefs import write_prefs

    write_prefs(theme="sepia")
    win = _open(seeded)
    try:
        assert win.theme.key == "cyan-neon" and win.theme_var.get() == "Cyan Neon"
        assert win.status_text().startswith("Warning:") and "sepia" in win.status_text()
    finally:
        _shut(win)


def test_theme_event_repaints_an_open_window(window, seeded):
    result = seeded.execute("theme", key="green-neon", actor="agent")
    assert result.ok, result.errors
    deadline = time.time() + 2
    while window.theme.key != "green-neon" and time.time() < deadline:
        window.update()
        time.sleep(0.02)
    assert window.theme.key == "green-neon" and window.theme_var.get() == "Green Neon"
    assert seeded.events.last(1)[0]["topic"] == "theme.changed"
    assert ttk.Style(window).lookup("TButton", "foreground") == window.theme.palette.primary


def test_fit_geometry_keeps_the_full_size_only_when_the_screen_holds_it():
    from asi_dewey.gui.main_window import DEFAULT_SIZE, fit_geometry

    assert DEFAULT_SIZE == (1280, 800)
    assert fit_geometry(1280, 800, 1920, 1080) == ("1280x800", False)
    assert fit_geometry(1280, 800, 1280, 800) == ("1264x700+0+0", True)  # a 1280x800 laptop: maximise
    assert fit_geometry(1280, 800, 1366, 768) == ("1280x668+0+0", True)
    assert fit_geometry(1280, 800, 1300, 900) == ("1280x800", False)


def test_window_opens_zoomed_or_at_full_size(window):
    geometry, zoom = fit_geometry_for(window)
    if zoom:
        assert window.state() in ("zoomed", "withdrawn")  # the fixture withdraws it
    else:
        assert window.winfo_reqwidth() <= 1280


def fit_geometry_for(window):
    from asi_dewey.gui.main_window import DEFAULT_SIZE, fit_geometry

    return fit_geometry(*DEFAULT_SIZE, window.winfo_screenwidth(), window.winfo_screenheight())



# -- JIRA Live Data (0.5.0): filled from a stubbed execute_quiet, no gateway, no network ---------
# Since 0.7.3 the verb runs on a worker thread, so every fetch is followed by ``wait_fetch()``,
# which pumps the Tk loop until the Result has been applied, and the stub never touches a widget.
def _issue(key, summary, issue_type, status, category, priority, assignee, due, labels=(), parent=None, res=None):
    number = key.split("-")[1]
    return {
        "key": key, "issue_type": issue_type, "summary": summary, "status": status, "status_category": category,
        "resolution": res, "priority": priority, "assignee": assignee, "reporter": "Bob", "labels": list(labels),
        "components": [], "parent_key": parent, "created": f"2026-10-0{number[-1]}T09:12:40.000-0600",
        "updated": "2026-10-27T11:18:59.416-0600", "due": due, "url": f"https://x.atlassian.net/browse/{key}",
    }


SAMPLE = {
    "jql": "project = HWL AND assignee = currentUser() ORDER BY updated DESC",
    "fetched_at": "2026-10-27T18:04:11+00:00", "count": 5,
    "truncated": False,
    "issues": [
        _issue("HWL-9", "Brake test on the loader", "Story", "In Progress", "indeterminate", "High", "Ada",
               "2026-11-01", labels=("safety", "VAT"), parent="HWL-1"),
        _issue("HWL-10", "E-stop latency", "Bug", "To Do", "new", "Low", "Ada", "2026-11-05"),
        _issue("HWL-100", "Hazard log review", "Story", "Done", "done", "High", "Cy", "2026-10-01", res="Done"),
        _issue("HWL-2", "Old defect", "Bug", "Done", "done", "Low", "Cy", "2026-09-01", res="Fixed"),
        _issue("HWL-33", "Unassigned work", "Story", "In Progress", "indeterminate", "High", None, None),
    ],
}
COMMENTS = {
    "key": "HWL-9", "summary": "Brake test on the loader", "url": "https://x.atlassian.net/browse/HWL-9",
    "status": "In Progress", "fetched_at": "2026-10-27T18:04:11+00:00", "count": 3,
    "comments": [
        {"id": "c3", "author": "Ada", "created": "2026-10-26T15:02:11.000-0600",
         "updated": "2026-10-26T15:40:00.000-0600", "body": "Reviewed the loss list; L3 needs work."},
        {"id": "c2", "author": "Bob", "created": "2026-10-24T09:00:00.000-0600",
         "updated": "2026-10-24T09:00:00.000-0600", "body": "Draft attached.\nSee the sheet."},
        {"id": "c1", "author": "Cy", "created": "2026-10-21T09:12:40.000-0600",
         "updated": "2026-10-21T09:12:40.000-0600", "body": "Opened."},
    ],
}
NO_SESSION = "no Atlassian session for this account; run `asi-hopper auth login` once"


class FakeExecuteQuiet:
    """Stands in for ``MainWindow.execute_quiet``: counts calls per action and records the calling thread.

    It runs on the screen's worker thread, so it touches no widget; the status bar is the real
    ``report_quiet``'s job. ``gate``, when set, holds every call until the test opens it, so a
    fetch can be observed in flight.
    """

    def __init__(self, window) -> None:
        self.window = window
        self.calls = {"live": 0, "comments": 0}
        self.fail: str | None = None
        self.gate: threading.Event | None = None
        self.threads: list[threading.Thread] = []

    def __call__(self, verb, **args):
        from asi_dewey.commands import Result

        assert verb == "jira"
        action = args["action"]
        self.calls[action] += 1
        self.threads.append(threading.current_thread())
        if self.gate is not None:
            self.gate.wait(5.0)
        if self.fail:
            return Result.failure(self.fail)
        if action == "live":
            return Result.success(SAMPLE)
        key = args["key"]
        if key == "HWL-9":
            return Result.success(COMMENTS)
        return Result.success({**COMMENTS, "key": key, "summary": "other", "count": 0, "comments": []})


@pytest.fixture
def stub(window, monkeypatch):
    fake = FakeExecuteQuiet(window)
    monkeypatch.setattr(window, "execute_quiet", fake)
    return fake


def _fetched(window):
    """The live screen shown and fetched once through the stub, the Result applied."""
    screen = window.show("jira_live")
    screen.fetch()
    assert screen.wait_fetch().ok
    return screen


def _settled(window, seconds: float = 0.1) -> None:
    """Pump the Tk loop for a while so any poll still pending has had its chance to fire."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        window.update()
        time.sleep(0.01)


def _view_labels(window):
    menubar = window.nametowidget(window.cget("menu"))
    tops = [i for i in range(menubar.index("end") + 1) if menubar.type(i) == "cascade"]
    view_menu = window.nametowidget(menubar.entrycget(tops[1], "menu"))
    entries = range(view_menu.index("end") + 1)
    return [view_menu.entrycget(i, "label") for i in entries if view_menu.type(i) == "command"]


def _texts(win):
    return [c for c in win.body.inner.winfo_children() if isinstance(c, tk.Text)]


def test_jira_live_is_second_in_nav_and_view(window):
    assert [k for k, _ in window.factory.items()][:2] == ["dashboard", "jira_live"]
    assert window.factory.title("jira_live") == "JIRA Live Data"
    assert _view_labels(window)[1] == "JIRA Live Data"
    assert window.nav.get(1).strip() == "JIRA LIVE DATA"


def test_jira_tile_opens_the_live_screen(window, stub):
    dash = window.current
    names = list(dash._tile_vars)
    tiles = dash.tiles.winfo_children()
    tiles[names.index("jira_ticket")].event_generate("<Button-1>", x=1, y=1)
    window.update()
    assert window.current_key == "jira_live" and stub.calls["live"] == 0  # the tile never connects
    assert window.current.status_var.get() == "No fetch yet · press Refresh"
    window.show("dashboard")
    tiles = window.current.tiles.winfo_children()
    tiles[names.index("fact")].event_generate("<Button-1>", x=1, y=1)
    window.update()
    assert window.current_key == "entity:fact"


def test_first_show_does_not_fetch_by_default(window, seeded, stub):
    assert "jira_live_autofetch" not in seeded.config  # the house default: no connection until Refresh
    screen = window.show("jira_live")
    _settled(window)
    assert stub.calls["live"] == 0 and screen.tree.get_children() == () and window.jira_live is None
    assert screen.status_var.get() == "No fetch yet · press Refresh"
    assert not screen.fetcher.running and not screen.refresh_button.instate(["disabled"])
    window.show("dashboard")
    assert window.show("jira_live") is screen
    _settled(window)
    assert stub.calls["live"] == 0 and window.jira_live is None


def test_first_show_fetches_once_when_configured(window, seeded, stub, monkeypatch):
    import re

    monkeypatch.setitem(seeded.config, "jira_live_autofetch", True)
    screen = window.show("jira_live")
    assert screen.fetcher.running  # the show started the fetch; the window is not blocked on it
    assert screen.wait_fetch().ok and stub.calls["live"] == 1
    assert window.status_text() == "Jira: 5 issues fetched"
    window.show("dashboard")  # its refresh rewrites the status bar with the database path
    assert window.show("jira_live") is screen
    _settled(window)
    assert stub.calls["live"] == 1
    assert window.jira_live.data is SAMPLE
    assert len(screen.tree.get_children()) == 5
    assert re.match(r"^5 issues · fetched \d\d:\d\d · project = HWL", screen.status_var.get())
    assert screen.count_var.get() == "5 of 5 issues"


def test_autofetch_off_waits_for_refresh(window, seeded, stub, monkeypatch):
    monkeypatch.setitem(seeded.config, "jira_live_autofetch", False)
    screen = window.show("jira_live")
    _settled(window)
    assert stub.calls["live"] == 0 and screen.tree.get_children() == ()
    assert screen.status_var.get() == "No fetch yet · press Refresh"
    assert screen.fetch() is None  # the button starts the worker and returns at once
    assert screen.wait_fetch().ok and len(screen.tree.get_children()) == 5 and stub.calls["live"] == 1


def test_fetch_runs_off_the_tk_thread_and_applies_on_it(window, stub, monkeypatch):
    screen = window.show("jira_live")
    refreshed_on: list[threading.Thread] = []
    original = screen.refresh
    monkeypatch.setattr(screen, "refresh", lambda: (refreshed_on.append(threading.current_thread()), original()))
    stub.gate = threading.Event()
    screen.fetch()
    # in flight: the Tk thread is free, the button is off, both labels say so, a second fetch is ignored
    assert screen.fetcher.running and screen.refresh_button.instate(["disabled"])
    assert screen.status_var.get() == "Fetching Jira … up to 2000 issues, this can take a minute"
    assert window.status_text() == "Fetching Jira …"
    _settled(window)  # the poll fires and finds the worker still busy
    screen.fetch()
    screen.refresh()  # a repaint while fetching (an entity event, a show) keeps the label
    assert screen.status_var.get().startswith("Fetching Jira …") and screen.tree.get_children() == ()
    assert stub.calls["live"] == 1 and screen.fetcher.running
    stub.gate.set()
    result = screen.wait_fetch()
    assert result.ok and result.data is SAMPLE and stub.calls["live"] == 1
    assert stub.threads and all(t is not threading.main_thread() for t in stub.threads)
    assert refreshed_on and refreshed_on[-1] is threading.main_thread()  # applied on the Tk thread
    assert not screen.fetcher.running and not screen.refresh_button.instate(["disabled"])
    assert len(screen.tree.get_children()) == 5 and window.status_text() == "Jira: 5 issues fetched"
    assert screen.status_var.get().startswith("5 issues · fetched")


def test_screen_destroyed_mid_fetch_drops_the_result(window, stub, monkeypatch):
    errors = []
    monkeypatch.setattr(window, "report_callback_exception", lambda *a: errors.append(a))
    screen = window.show("jira_live")
    stub.gate = threading.Event()
    screen.fetch()
    worker = screen.fetcher.thread
    assert window.pick_theme("pink-noir").ok  # rebuilds every screen while the worker is busy; no join
    assert not screen.winfo_exists() and worker.is_alive()
    rebuilt = window.current
    assert rebuilt is not screen and rebuilt.status_var.get() == "No fetch yet · press Refresh"
    stub.gate.set()
    worker.join(5.0)
    assert not worker.is_alive()
    _settled(window)
    assert errors == [] and window.jira_live is None and rebuilt.tree.get_children() == ()
    assert stub.calls["live"] == 1 and screen.fetcher.last.ok  # produced, then dropped


def test_refresh_keeps_rows_when_the_fetch_fails(window, seeded, stub, monkeypatch):
    screen = _fetched(window)
    screen.fetch()
    assert screen.wait_fetch().ok and stub.calls["live"] == 2
    stub.fail = NO_SESSION
    screen.fetch()
    assert not screen.wait_fetch().ok
    assert len(screen.tree.get_children()) == 5 and window.jira_live.ok
    assert window.status_text().startswith("Error: no Atlassian session")
    # a fresh window whose configured first fetch fails: empty table, Offline label, no second fetch on show
    monkeypatch.setitem(seeded.config, "jira_live_autofetch", True)
    fresh = _open(seeded)
    try:
        fake = FakeExecuteQuiet(fresh)
        fake.fail = NO_SESSION
        fresh.execute_quiet = fake
        screen = fresh.show("jira_live")
        assert not screen.wait_fetch().ok
        assert screen.tree.get_children() == () and screen.status_var.get().startswith("Offline:")
        assert fresh.jira_live is not None and not fresh.jira_live.ok
        fresh.show("dashboard")
        fresh.show("jira_live")
        _settled(fresh)
        assert fake.calls["live"] == 1
    finally:
        _shut(fresh)


def test_sorting_is_numeric_on_keys_and_nulls_last(window, stub):
    screen = _fetched(window)
    screen.sort_by("key")
    assert screen.tree.get_children() == ("HWL-2", "HWL-9", "HWL-10", "HWL-33", "HWL-100")
    assert screen.tree.heading("key", "text").endswith("▲")
    screen.sort_by("key")
    assert screen.tree.get_children() == ("HWL-100", "HWL-33", "HWL-10", "HWL-9", "HWL-2")
    assert screen.tree.heading("key", "text").endswith("▼") and screen.tree.heading("due", "text") == "Due"
    screen.sort_by("due")
    assert screen.tree.get_children() == ("HWL-2", "HWL-100", "HWL-9", "HWL-10", "HWL-33")
    screen.sort_by("due")
    assert screen.tree.get_children() == ("HWL-10", "HWL-9", "HWL-100", "HWL-2", "HWL-33")
    screen.clear_filters()
    assert screen.tree.get_children() == ("HWL-9", "HWL-10", "HWL-100", "HWL-2", "HWL-33")  # server order


def test_filters_are_local_and_combine(window, stub):
    screen = _fetched(window)
    screen.filter_var.set("hwl-1")
    assert screen.tree.get_children() == ("HWL-10", "HWL-100")
    screen.filter_var.set("brake")
    assert screen.tree.get_children() == ("HWL-9",)
    screen.filter_var.set("")
    screen.filters["status"].set("Done")
    screen._populate()
    assert screen.tree.get_children() == ("HWL-100", "HWL-2") and screen.count_var.get() == "2 of 5 issues"
    assert list(screen.filter_boxes["status_category"]["values"]) == ["(all)", "new", "indeterminate", "done"]
    assert list(screen.filter_boxes["assignee"]["values"]) == ["(all)", "Ada", "Cy", "(none)"]
    screen.filters["status"].set("(all)")
    screen.filters["assignee"].set("(none)")
    screen._populate()
    assert screen.tree.get_children() == ("HWL-33",)
    screen.filters["assignee"].set("(all)")
    screen.filters["issue_type"].set("Bug")
    screen._populate()
    assert screen.tree.get_children() == ("HWL-10", "HWL-2")
    screen.filters["priority"].set("Low")
    screen.filters["status_category"].set("done")
    screen._populate()
    assert screen.tree.get_children() == ("HWL-2",)  # AND
    screen.clear_filters()
    assert len(screen.tree.get_children()) == 5 and all(v.get() == "(all)" for v in screen.filters.values())
    assert stub.calls["live"] == 1  # filters never re-query


def test_done_rows_are_muted_and_cells_are_shaped(window, stub):
    screen = _fetched(window)
    for iid in screen.tree.get_children():
        tags = screen.tree.item(iid, "tags")
        assert ("muted" in tags) == (iid in ("HWL-100", "HWL-2"))
        assert ("odd" in tags) != ("even" in tags)
    assert str(screen.tree.tag_configure("muted", "foreground")) == window.theme.palette.muted
    assert screen.tree.set("HWL-9", "labels") == "safety, VAT"
    assert screen.tree.set("HWL-9", "comments") == "[Comments]"
    assert len(screen.tree.set("HWL-9", "created")) == 10
    assert screen.tree.set("HWL-33", "assignee") == "" and screen.tree.set("HWL-33", "due") == ""


def test_open_selected_reports_the_url_when_not_interactive(window, stub):
    screen = _fetched(window)
    screen.open_selected()
    assert window.status_text() == "Select an issue first"
    screen.tree.focus("HWL-9")
    screen.open_selected()
    assert window.status_text() == "Open: https://x.atlassian.net/browse/HWL-9"


def test_theme_rebuild_keeps_the_fetch(window, stub):
    _fetched(window)
    assert window.pick_theme("pink-noir").ok
    assert window.current_key == "jira_live" and stub.calls["live"] == 1
    screen = window.current
    assert len(screen.tree.get_children()) == 5
    assert str(screen.tree.tag_configure("muted", "foreground")) == "#955073"  # pink-noir's muted


def test_jira_live_event_does_not_refresh_screens(window, seeded):
    assert window.current_key == "dashboard"
    seeded.events.publish("jira.live", count=0, jql="x", truncated=False, fetched_at="", actor="agent")
    assert window._refresh_job is None
    seeded.events.publish("entity.created", entity="fact", id=99, actor="agent")
    assert window._refresh_job is not None
    window._cancel_refresh()
    assert seeded.execute("count", entity="jira_ticket").data["count"] == 0


# -- the Comments column and the comments window ------------------------------------------
def test_comments_click_is_routed_by_column(window, stub, monkeypatch):
    from types import SimpleNamespace

    screen = _fetched(window)
    monkeypatch.setattr(screen.tree, "identify_column", lambda x: "#1")
    monkeypatch.setattr(screen.tree, "identify_row", lambda y: "HWL-9")
    assert screen._on_click(SimpleNamespace(x=5, y=5)) == "break"
    assert "HWL-9" in window.comment_windows
    assert window.comment_windows["HWL-9"].wait_fetch().ok and stub.calls["comments"] == 1
    monkeypatch.setattr(screen.tree, "identify_column", lambda x: "#3")
    assert screen._on_click(SimpleNamespace(x=5, y=5)) is None and len(window.comment_windows) == 1
    screen.tree.focus("HWL-10")
    screen._on_key_c(None)
    assert set(window.comment_windows) == {"HWL-9", "HWL-10"}
    assert window.comment_windows["HWL-10"].wait_fetch().ok and stub.calls["comments"] == 2


def test_comments_window_lists_newest_first(window, stub, seeded):
    import re

    win = window.open_comments("HWL-9")
    assert win.wait_fetch().ok
    assert win.title() == "HWL-9 — Comments" and win.cget("background") == window.theme.palette.bg
    children = win.body.inner.winfo_children()
    metas = [c.cget("text") for c in children if isinstance(c, ttk.Label)]
    assert metas[0].startswith("Ada · 2026-10-26 15:02") and metas[0].endswith("· edited 2026-10-26 15:40")
    assert metas[1] == "Bob · 2026-10-24 09:00" and metas[2] == "Cy · 2026-10-21 09:12"
    texts = _texts(win)
    assert [str(t.cget("state")) for t in texts] == ["disabled"] * 3
    assert texts[1].get("1.0", "end").strip() == "Draft attached.\nSee the sheet."
    assert re.match(r"^3 comments · fetched \d\d:\d\d$", win.status_var.get())
    # second open: the same window comes to the front
    assert window.open_comments("HWL-9") is win and len(window.comment_windows) == 1
    assert window.open_comments("HWL-10").wait_fetch().ok
    assert len(window.comment_windows) == 2
    # refresh, then a failed refresh keeps the blocks and the window
    assert win.fetch() is None
    assert win.wait_fetch().ok and stub.calls["comments"] == 3 and len(_texts(win)) == 3
    stub.fail = NO_SESSION
    win.fetch()
    assert not win.wait_fetch().ok and len(_texts(win)) == 3
    assert win.status_var.get().startswith("Error: no Atlassian session") and win.winfo_exists()
    assert window.status_text().startswith("Error:")
    stub.fail = None
    # empty history
    empty = window.open_comments("HWL-2")
    assert empty.wait_fetch().ok
    labels = [c.cget("text") for c in empty.body.inner.winfo_children() if isinstance(c, ttk.Label)]
    assert labels == ["No comments."]
    # close, then a theme pick destroys the rest
    empty.close()
    assert "HWL-2" not in window.comment_windows and not empty.winfo_exists()
    destroyed = []
    win.bind("<Destroy>", lambda e: destroyed.append(1))
    assert window.pick_theme("pink-noir").ok
    assert window.comment_windows == {} and destroyed
    assert seeded.execute("count", entity="jira_ticket").data["count"] == 0


def test_comments_fetch_runs_off_the_tk_thread(window, stub, monkeypatch):
    errors = []
    monkeypatch.setattr(window, "report_callback_exception", lambda *a: errors.append(a))
    stub.gate = threading.Event()
    win = window.open_comments("HWL-9")
    # in flight: the window is live, its button is off, its label says so, a second fetch is ignored
    assert win.fetcher.running and win.refresh_button.instate(["disabled"])
    assert win.status_var.get() == "Fetching comments …"
    _settled(window)
    win.fetch()
    assert stub.calls["comments"] == 1 and win.fetcher.running
    stub.gate.set()
    assert win.wait_fetch().ok and stub.calls["comments"] == 1
    assert stub.threads and all(t is not threading.main_thread() for t in stub.threads)
    assert not win.refresh_button.instate(["disabled"]) and len(_texts(win)) == 3
    assert win.status_var.get().startswith("3 comments · fetched")
    # closed mid-fetch: nothing joins the worker and its Result is dropped without a callback error
    stub.gate = threading.Event()
    other = window.open_comments("HWL-10")
    worker = other.fetcher.thread
    other.close()
    assert not other.winfo_exists() and "HWL-10" not in window.comment_windows and worker.is_alive()
    stub.gate.set()
    worker.join(5.0)
    assert not worker.is_alive()
    _settled(window)
    assert errors == [] and stub.calls["comments"] == 2 and other.fetcher.last.ok


def test_comment_windows_close_with_the_main_window(seeded):
    win = _open(seeded)
    win.execute_quiet = FakeExecuteQuiet(win)
    comments = win.open_comments("HWL-9")
    assert comments.wait_fetch().ok
    destroyed = []
    comments.bind("<Destroy>", lambda e: destroyed.append(1))
    _shut(win)
    assert destroyed


def test_gui_main_returns_3_without_a_window_while_a_holder_runs(hold, tmp_path, monkeypatch):
    from asi_dewey.gui import app
    from tests.conftest import HOLD_BRAIN

    hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0")
    monkeypatch.setattr(app, "ask_retry", lambda exc: pytest.fail("no dialog when not interactive"))
    monkeypatch.setattr(app, "launch", lambda *a, **k: pytest.fail("no window while refused"))
    assert app.main(["--db", str(tmp_path / "gui.db")], interactive=False) == 3
    assert not (tmp_path / "gui.db").exists()


def test_gui_retry_dialog_quits_or_retries(hold, tmp_path, monkeypatch):
    from asi_dewey.gui import app
    from tests.conftest import HOLD_BRAIN

    holder = hold(HOLD_BRAIN, str(tmp_path / "held.db"), "0")
    asked: list[str] = []

    def quit_(exc):
        asked.append(exc.slot)
        return False

    monkeypatch.setattr(app, "ask_retry", quit_)
    monkeypatch.setattr(app, "launch", lambda *a, **k: pytest.fail("no window while refused"))
    assert app.main(["--db", str(tmp_path / "gui.db")]) == 3 and asked == ["family"]

    def retry_then_free(exc):
        asked.append("retry")
        holder.release()
        return True

    launched: list[object] = []
    monkeypatch.setattr(app, "ask_retry", retry_then_free)
    monkeypatch.setattr(app, "launch", lambda brain, **k: launched.append(brain))
    assert app.main(["--db", str(tmp_path / "gui.db")]) == 0
    assert asked == ["family", "retry"] and len(launched) == 1


def test_about_names_the_lock_directory(window):
    from asi_dewey.locks import lock_dir

    window.about()
    assert str(lock_dir()) in window.status_text() and "Lock directory:" in window.status_text()


# -- the status bar: online indicator with the automation port, and the theme badge (0.7.0) --------
def test_theme_badge_text():
    from asi_dewey.gui.main_window import theme_badge

    assert theme_badge("Cyan Neon") == "CYAN NEON" and theme_badge("Pink Day") == "PINK DAY"
    assert theme_badge("Plain (native)") == "PLAIN" and theme_badge("Gold Noir") == "GOLD NOIR"


def test_badge_follows_the_theme_and_sits_between_indicator_and_status(window):
    assert window.badge_var.get() == "CYAN NEON"
    assert str(window.badge_label.cget("style")) == "StatusMuted.TLabel"
    font = str(window.badge_label.cget("font"))
    assert window.theme.mono[0] in font and str(window.theme.mono[1]) in font  # the mono font
    bar = window.badge_label.master
    labels = [w for w in bar.winfo_children() if isinstance(w, ttk.Label)]
    assert labels[0] is window.online_label and labels[1] is window.badge_label
    assert str(labels[2].cget("textvariable")) == str(window.status_var)
    assert window.pick_theme("plain").ok and window.badge_var.get() == "PLAIN"
    assert window.pick_theme("gold-day").ok and window.badge_var.get() == "GOLD DAY"
    assert str(window.badge_label.cget("style")) == "StatusMuted.TLabel"


def test_online_indicator_names_the_port_and_the_server_survives_a_rebuild(window):
    import json

    from asi_dewey.automation.session import session_path

    server = window.server
    assert server is not None and window.online_var.get() == f"◉ ONLINE :{server.port}"
    assert json.loads(session_path().read_text(encoding="utf-8"))["port"] == server.port
    assert window.pick_theme("violet-dusk").ok
    assert window.server is server and window.online_var.get() == f"◉ ONLINE :{server.port}"
    # the pump is alive after the rebuild: a job posted from another thread is answered
    answered = []
    import threading

    thread = threading.Thread(target=lambda: answered.append(server.on_main(lambda: window.theme.key)), daemon=True)
    thread.start()
    deadline = time.time() + 5
    while thread.is_alive() and time.time() < deadline:
        window.update()
        time.sleep(0.01)
    assert answered == ["violet-dusk"]


# -- Column widths (0.7.1): every table column fits its widest text, heading and lookups included ---
def _tree_fonts(tree):
    import tkinter.font as tkfont

    style = ttk.Style(tree)
    cells = tkfont.Font(tree, font=style.lookup("Treeview", "font") or "TkDefaultFont")
    headings = tkfont.Font(tree, font=style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    return cells, headings


def _assert_fitted(tree, extra=None, padding=24, max_width=600):
    """Every column is at least as wide as its widest heading, cell or extra value plus padding, or the cap."""
    cells, headings = _tree_fonts(tree)
    for column in tree["columns"]:
        widest = headings.measure(tree.heading(column, "text"))
        for iid in tree.get_children(""):
            widest = max(widest, cells.measure(str(tree.set(iid, column))))
        for text in (extra or {}).get(column, ()):
            widest = max(widest, cells.measure(text))
        assert int(tree.column(column, "width")) >= min(widest + padding, max_width), column


def test_fit_columns_measures_heading_cells_and_extra(window):
    from asi_dewey.gui.screens import fit_columns

    tree = ttk.Treeview(window, columns=("a", "b", "c", "d", "e"), show="headings")
    tree.heading("a", text="n")
    tree.heading("b", text="A long heading that is wider than any of its cells")
    tree.heading("c", text="c")
    tree.heading("d", text="d")
    tree.heading("e", text="")
    long_cell = "a cell that is quite a lot longer than its heading"
    extra_value = "an extra value that no row holds"
    tree.insert("", "end", values=(long_cell, "x", "y" * 400, "short", ""))
    tree.insert("", "end", values=("short", "xx", "", "", ""))
    cells, headings = _tree_fonts(tree)
    widths = fit_columns(tree, {"d": (extra_value,)}, min_width=40, max_width=600, padding=24)
    assert widths["a"] == cells.measure(long_cell) + 24  # the cell wins over a short heading
    assert widths["b"] == headings.measure(tree.heading("b", "text")) + 24  # the heading wins
    assert widths["c"] == 600 and cells.measure("y" * 400) + 24 > 600  # capped at max_width
    assert widths["d"] == cells.measure(extra_value) + 24  # extra widens a column with no such cell
    assert widths["e"] == 40  # an empty column is floored at min_width
    for column, width in widths.items():
        assert int(tree.column(column, "width")) == width
        assert int(tree.column(column, "minwidth")) == width and not tree.column(column, "stretch")
    tree.destroy()


def test_entity_screen_columns_fit_their_text(window):
    screen = window.show("entity:fact")
    assert len(screen.tree.get_children()) == 2
    _assert_fitted(screen.tree, screen._lookup_values())
    screen.search_var.set("Product")  # every repopulate refits
    assert len(screen.tree.get_children()) == 1
    _assert_fitted(screen.tree, screen._lookup_values())


def test_enum_column_fits_the_longest_lookup_value(window, seeded):
    screen = window.show("entity:link")
    cells, _ = _tree_fonts(screen.tree)
    assert [screen.tree.set(i, "link_class") for i in screen.tree.get_children()] == ["tool"]
    longest = max(seeded.lookups["link_class"], key=cells.measure)
    assert longest == "MS Windows software" and cells.measure(longest) > cells.measure("tool")
    assert int(screen.tree.column("link_class", "width")) >= cells.measure(longest) + 24


def test_jira_live_columns_fit_their_text(window, stub):
    screen = _fetched(window)
    assert len(screen.tree.get_children()) == 5 and screen.tree.set("HWL-9", "comments") == "[Comments]"
    _assert_fitted(screen.tree)
    screen.sort_by("summary")  # the sort marker is part of the heading; a repaint refits
    _assert_fitted(screen.tree)
    assert not screen.tree.column("summary", "stretch")  # a fitted column never shrinks below its text


def test_dashboard_columns_fit_their_text(window):
    dash = window.current
    assert dash.key == "dashboard"
    dash.refresh()
    assert dash.audit.get_children()  # the seeded creates are in the audit tail: real cells were measured
    for tree in (dash.jira, dash.tasks, dash.audit):
        _assert_fitted(tree)
