from __future__ import annotations

import gc
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
    assert keys[:8] == [
        "dashboard", "entity:task", "entity:fact", "entity:machine_function", "entity:use_case",
        "entity:link", "entity:qms_document", "entity:person",
    ]
    assert keys[-2:] == ["transfer", "generate"] and "stpa" in keys  # the STPA analyses screen (0.10.0)
    assert [k for k in keys if k.startswith("entity:")] == keys[1:8]  # no other entity has a table of its own
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
    assert window.status_text() == f"Fact {first} selected"
    screen.duplicate()
    assert screen.selected_id is None and screen.widgets["order"].get() is None


def test_pruned_screens_are_absent(window, seeded):
    from asi_dewey.errors import NotFound
    from asi_dewey.gui.screens import HIDDEN_ENTITY_SCREENS

    assert HIDDEN_ENTITY_SCREENS == frozenset({  # the control structure, the STPA analysis and their parts: own screens
        "jira_ticket", "safety_plan_row",
        "control_structure", "cs_controller", "cs_algorithm", "cs_process_model_entry", "cs_edge", "cs_signal",
        "cs_note",
        "stpa_analysis", "stpa_loss", "stpa_hazard", "stpa_uca", "stpa_scenario", "stpa_constraint",
    })
    keys = [k for k, _ in window.factory.items()]
    for key in ("entity:jira_ticket", "entity:safety_plan_row", "safety_plan_matrix"):
        assert key not in keys and key not in window.factory
    assert sum(k.startswith("entity:") for k in keys) == 7  # seven after the prune; JIRA Live Data went in 0.8.1
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
    assert window.nav.size() == len(keys)
    rows = [row.strip() for row in window.nav.get(0, "end")]
    assert "JIRA" not in rows and not any(row.startswith("SAFETY PLAN") for row in rows)
    # the entities stay: tables, commands and counts are untouched
    assert "jira_ticket" in seeded.registry and "safety_plan_row" in seeded.registry
    assert len(seeded.registry) == 22
    assert seeded.execute("count", entity="safety_plan_row").data["count"] == 1
    # the dashboard still counts both; neither tile is clickable: no screen opens for a hidden entity
    dash = window.current
    assert dash._tile_vars["safety_plan_row"].get() == "1" and dash._tile_vars["jira_ticket"].get() == "0"
    names = list(dash._tile_vars)
    tiles = dash.tiles.winfo_children()
    assert tiles[names.index("safety_plan_row")].bind("<Button-1>") == ""
    assert tiles[names.index("jira_ticket")].bind("<Button-1>") == ""  # it opened the live view until 0.8.1
    assert tiles[names.index("fact")].bind("<Button-1>") != ""


def test_hidden_set_must_name_registered_entities(seeded):
    from asi_dewey.gui.screens import build_default_screens

    with pytest.raises(ValueError):
        build_default_screens(seeded, hidden=frozenset({"unicorn"}))
    keys = [k for k, _ in build_default_screens(seeded, hidden=frozenset()).items()]
    assert sum(k.startswith("entity:") for k in keys) == len(seeded.registry) == 22  # every entity gets a table
    assert "entity:jira_ticket" in keys and "entity:safety_plan_row" in keys and "entity:stpa_uca" in keys


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
    with pytest.raises(ValueError, match="uid is a hidden field"):  # no widget for a hidden field (0.8.0)
        factory.create(window, task.field("uid"))


def _point_at(monkeypatch, screen, iid: str, column: str):
    """Point the screen's tree at the cell ``(iid, column)`` (a withdrawn window has no geometry to hit-test)
    and return a fake pointer event."""
    from types import SimpleNamespace

    number = screen.columns.index(column) + 1
    monkeypatch.setattr(screen.tree, "identify_column", lambda x: f"#{number}")
    monkeypatch.setattr(screen.tree, "identify_row", lambda y: iid)
    monkeypatch.setattr(screen.tree, "identify_region", lambda x, y: "cell")
    return SimpleNamespace(x=5, y=5)


def test_url_cell_click_opens_the_link_and_selects_the_row(window, seeded, monkeypatch):
    screen = window.show("entity:link")
    assert screen.url_columns == ["url"]
    row_id = seeded.execute("list", entity="link").data[0]["id"]
    event = _point_at(monkeypatch, screen, str(row_id), "url")
    assert screen._on_click(event) == "break"
    assert screen.selected_id == row_id and window.status_text() == "Open: https://x.y/z"
    screen._on_motion(event)
    assert str(screen.tree.cget("cursor")) == "hand2"
    name_event = _point_at(monkeypatch, screen, str(row_id), "name")
    assert screen._on_click(name_event) is None  # another column: normal selection, no browser
    screen._on_motion(name_event)
    assert str(screen.tree.cget("cursor")) == ""


def test_url_cell_without_a_value_is_not_a_link(window, seeded, monkeypatch):
    created = seeded.execute("create", entity="qms_document", data={"name": "QP-11", "order": 1}).data
    screen = window.show("entity:qms_document")
    assert screen.url_columns == ["url"]
    window.set_status("")
    assert screen._on_click(_point_at(monkeypatch, screen, str(created["id"]), "url")) is None
    assert window.status_text() == ""


def test_url_widget_ctrl_click_and_open_report_through_the_screen(window, seeded):
    screen = window.show("entity:qms_document")
    widget = screen.widgets["url"]
    widget.set("https://qms.example/QP-11")
    widget.open()
    assert window.status_text() == "Open: https://qms.example/QP-11"
    window.set_status("")
    assert widget._ctrl_click(None) == "break"
    assert window.status_text() == "Open: https://qms.example/QP-11"
    widget.set("")
    window.set_status("")
    widget.open()
    assert window.status_text() == ""  # nothing to open


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
        "schema_map", "lifecycle_overview", "phase_flow", "task_flow", "stpa_trace",
    ]
    assert [s["key"] for s in screen.catalog["document"]] == [
        "safety_plan", "status_report", "handbook", "stpa_report",
    ]
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



# -- the `jira.live` event (a forwarded `jira live`) changes no row, so it refreshes no screen --------
def test_jira_live_event_does_not_refresh_screens(window, seeded):
    assert window.current_key == "dashboard"
    seeded.events.publish("jira.live", count=0, jql="x", truncated=False, fetched_at="", actor="agent")
    assert window._refresh_job is None
    seeded.events.publish("entity.created", entity="fact", id=99, actor="agent")
    assert window._refresh_job is not None
    window._cancel_refresh()
    assert seeded.execute("count", entity="jira_ticket").data["count"] == 0


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


def test_dashboard_columns_fit_their_text(window):
    dash = window.current
    assert dash.key == "dashboard"
    dash.refresh()
    assert dash.audit.get_children()  # the seeded creates are in the audit tail: real cells were measured
    for tree in (dash.jira, dash.tasks, dash.audit):
        _assert_fitted(tree)


# -- the hidden identity in the window (0.8.0, docs/hidden-identity-plan.md, 3.3) ----------------
def _trees(widget):
    """Every ``ttk.Treeview`` under ``widget``, depth first."""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Treeview):
            found.append(child)
        found.extend(_trees(child))
    return found


def test_no_table_on_any_screen_has_an_id_order_or_uid_column(window):
    seen = 0
    for key, _ in window.factory.items():
        screen = window.show(key)
        trees = _trees(screen)
        if key.startswith("entity:") or key == "dashboard":
            assert trees, key
        for tree in trees:
            columns = set(tree.tk.splitlist(tree["columns"]))
            assert not columns & {"id", "order", "uid"}, (key, columns)
            seen += 1
    assert seen >= 10  # seven entity tables, three dashboard tables
    dash = window.show("dashboard")
    assert tuple(dash.audit["columns"]) == ("ts", "actor", "action", "entity", "entity_id")  # the trace stays


def test_entity_screen_columns_are_the_visible_fields_minus_order(window, seeded):
    from asi_dewey.gui.entity_screen import MAX_FLAG_COLUMNS, EntityScreen

    assert MAX_FLAG_COLUMNS == 8
    for schema in seeded.registry:
        key = f"entity:{schema.name}"
        screen = window.show(key) if key in window.factory else EntityScreen(window, window, schema)
        flags = [f for f in schema.visible_fields if f.is_flag]
        expected = [
            f.name for f in schema.visible_fields
            if f.name != "order" and (not f.is_flag or len(flags) <= MAX_FLAG_COLUMNS)
        ]
        assert screen.columns == expected, schema.name
        assert tuple(screen.tree.tk.splitlist(screen.tree["columns"])) == tuple(expected)
        assert "id" not in screen.columns and "uid" not in screen.columns and "order" not in screen.columns
        assert [screen.tree.heading(c, "text") for c in screen.columns] == [schema.field(c).header for c in expected]
        assert "uid" not in screen.widgets and ("order" in screen.widgets) == schema.has("order")
        assert set(screen.widgets) == {f.name for f in schema.visible_fields}
        if key not in window.factory:  # the HIDDEN_ENTITY_SCREENS, built here only to check the rule
            assert schema.name in ("jira_ticket", "safety_plan_row") or schema.name.startswith(
                ("cs_", "control_", "stpa_")
            )
            if schema.name == "safety_plan_row":
                assert len(flags) > MAX_FLAG_COLUMNS and not any(schema.field(c).is_flag for c in screen.columns)
            screen.destroy()
    link = window.show("entity:link")
    assert link.columns == ["link_class", "name", "url"] and link.url_columns == ["url"]
    fact = window.show("entity:fact")
    assert fact.columns == ["name", "text"] and fact.sort_key is None
    rows = [fact.by_id[int(i)]["order"] for i in fact.tree.get_children()]
    assert rows == sorted(rows)  # order is still the default sort, without a column


def test_details_title_names_the_selected_row(window, seeded):
    screen = window.show("entity:fact")
    assert screen.form_box.cget("text") == "Fact details"
    first = int(screen.tree.get_children()[0])
    screen.select(first)
    assert screen.form_box.cget("text") == f"Fact details · row {first}"
    assert window.status_text() == f"Fact {first} selected"
    screen.duplicate()
    assert screen.form_box.cget("text") == f"Fact details · copy of row {first}" and screen.selected_id is None
    screen.widgets["name"].set("Copy")
    screen.save()
    copy = screen.selected_id
    assert copy not in (None, first) and screen.form_box.cget("text") == f"Fact details · row {copy}"
    uids = {seeded.execute("get", entity="fact", id=i).data["uid"] for i in (first, copy)}
    assert len(uids) == 2  # a duplicate is a new row, so a new uid
    screen.new()
    assert screen.form_box.cget("text") == "Fact details" and screen.selected_id is None
    screen.select(copy)
    screen.delete()
    assert screen.form_box.cget("text") == "Fact details" and f"Deleted fact {copy}" == window.status_text()
    # the tree iids are still the ids
    assert {int(i) for i in screen.tree.get_children()} == {r["id"] for r in seeded.execute("list", entity="fact").data}


def test_scrollbar_thumb_is_the_primary(window):
    """Owner, 2026-10-29: the slider of a scrollbar is the dimmed primary at rest and the neon while dragged."""
    from tkinter import ttk

    style = ttk.Style(window)
    p = window.theme.palette
    assert style.lookup("TScrollbar", "background") == p.primary_dim
    assert style.lookup("TScrollbar", "troughcolor") == p.bg  # the trough is the background, the thumb stands on it
    assert dict(style.map("TScrollbar", "background")) == {"active": p.primary}


def test_mouse_wheel_over_a_combobox_never_picks_a_value(window, seeded):
    """0.8.3, found in asi_kletz 0.15.2: Tk's TCombobox class binding picks the next value on the wheel while
    the form scrolls on the same wheel, so a task class could change under a scrolling pointer and the next
    Save would store it. The window drops that binding (and the spinbox's) at start."""
    screen = window.show("entity:task")
    screen.select(1)
    widget = screen.widgets["task_class"]
    assert widget.get() == "administrative"
    assert window.bind_class("TCombobox", "<MouseWheel>") == ""
    assert window.bind_class("TSpinbox", "<MouseWheel>") == ""
    widget.combo.focus_set()
    widget.combo.event_generate("<MouseWheel>", delta=-120)  # wheel down, the pointer over the box
    widget.combo.event_generate("<MouseWheel>", delta=-120)
    assert widget.get() == "administrative" and screen.form_data()["task_class"] == "administrative"
    # the same wheel with Tk's stock binding back on: the value moves, which is what the window prevents
    window.bind_class("TCombobox", "<MouseWheel>", "ttk::combobox::Scroll %W [expr {-%D / 120}]")
    try:
        widget.combo.event_generate("<MouseWheel>", delta=-120)
        assert widget.get() == "status"
    finally:
        window.unbind_class("TCombobox", "<MouseWheel>")
    assert screen.form_data()["task_class"] == "status"  # the test moved it; the row in the database did not
    assert seeded.execute("get", entity="task", id=1).data["task_class"] == "administrative"
