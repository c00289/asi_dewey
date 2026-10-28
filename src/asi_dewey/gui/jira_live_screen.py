"""JiraLiveScreen: the JIRA Live Data window. One Refresh button, one big table, local filters.

The screen shows Jira and never changes it or stores what it shows. The one action that touches
Jira is ``fetch`` (the Refresh button; also the first show of a session, but only when
``jira_live_autofetch = true`` in ``dewey.toml``: by default the screen connects to nothing until
Refresh is pressed). The verb ``jira live`` runs on a daemon worker thread through
``MainWindow.execute_quiet`` (``WorkerFetch``): a fetch is up to 2000 issues at 50 a page, tens of
seconds on a good link, so it must not run on the Tk thread, which only polls and applies the
Result when it is in. The Result lives on the window object (``window.jira_live``) so a theme
pick, which rebuilds every screen, repaints without a refetch. Filters and sorting are applied to
the last fetch in memory, never as a re-query.

The ``[Comments]`` cell of every row is the per-row button: ``ttk.Treeview`` has no cell widgets,
so the click is routed by position (``identify_column`` / ``identify_row``) to
``MainWindow.open_comments``. The convention (key, title, verbs, columns, filters) is shared by
name with asi_kletz; see ``docs/jira-live-data-plan.md``.
"""

from __future__ import annotations

import datetime as dt
import re
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..commands import Result
from ..services.jira_service import LIVE_LIMIT
from .screens import Screen, WorkerFetch, fit_columns

if TYPE_CHECKING:
    from .main_window import MainWindow

COMMENTS_CELL = "[Comments]"
COMMENTS_COLUMN = "#1"  # the Treeview's display index of the first column
ALL = "(all)"
NONE = "(none)"
NO_FETCH_TEXT = "No fetch yet · press Refresh"
FETCHING_TEXT = f"Fetching Jira … up to {LIVE_LIMIT} issues, this can take a minute"
SUMMARY_TRUNCATE = 90
CATEGORY_ORDER = ("new", "indeterminate", "done")
DATE_COLUMNS = ("created", "updated", "due")
# column id, heading, starting width, stretch; fit_columns resizes every column after each fill
COLUMNS: tuple[tuple[str, str, int, bool], ...] = (
    ("comments", "Comments", 90, False),
    ("key", "Key", 90, False),
    ("issue_type", "Type", 90, False),
    ("summary", "Summary", 420, True),
    ("status", "Status", 130, False),
    ("status_category", "Category", 110, False),
    ("priority", "Priority", 100, False),
    ("assignee", "Assignee", 150, False),
    ("reporter", "Reporter", 150, False),
    ("labels", "Labels", 160, False),
    ("parent_key", "Parent", 90, False),
    ("created", "Created", 100, False),
    ("updated", "Updated", 100, False),
    ("due", "Due", 100, False),
    ("resolution", "Resolution", 110, False),
)
COLUMN_IDS = tuple(c[0] for c in COLUMNS)
FILTER_FIELDS: tuple[tuple[str, str], ...] = (
    ("status", "Status"),
    ("status_category", "Category"),
    ("issue_type", "Type"),
    ("priority", "Priority"),
    ("assignee", "Assignee"),
)
_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)-(\d+)$")


def cell_text(column: str, row: dict[str, Any]) -> str:
    """The text of one cell: ``None`` is empty, lists are joined, dates are cut to the day."""
    if column == "comments":
        return COMMENTS_CELL
    value = row.get(column)
    if value is None:
        return ""
    if column in ("labels", "components"):
        return ", ".join(str(v) for v in value)
    text = str(value).replace("\n", " ")
    if column == "summary" and len(text) > SUMMARY_TRUNCATE:
        return text[: SUMMARY_TRUNCATE - 1] + "…"
    if column in DATE_COLUMNS:
        return text[:10]
    return text


def sort_value(column: str, row: dict[str, Any]) -> Any:
    """The sort key of one row on ``column``; ``None`` is reported by the caller, not here."""
    value = row.get(column)
    if column == "key" and isinstance(value, str):
        match = _KEY_RE.match(value)
        if match:
            return (match.group(1).casefold(), int(match.group(2)), "")
        return (value.casefold(), 0, value.casefold())
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value).casefold()
    if isinstance(value, str):
        return value.casefold()
    return value


def local_clock(stamp: str | None) -> str:
    """``fetched_at`` (UTC ISO 8601) -> ``hh:mm`` local; an unparsable stamp shows as ``--:--``."""
    try:
        return dt.datetime.fromisoformat(stamp or "").astimezone().strftime("%H:%M")
    except ValueError:
        return "--:--"


class JiraLiveScreen(Screen):
    def __init__(self, master: tk.Misc, window: MainWindow) -> None:
        self.sort_column: str | None = None
        self.sort_desc = False
        self.filters: dict[str, tk.StringVar] = {}
        self.filter_boxes: dict[str, ttk.Combobox] = {}
        self._rows_by_key: dict[str, dict[str, Any]] = {}
        self._cursor = ""
        self.fetcher = WorkerFetch(self, self._apply)
        super().__init__(master, window)

    # -- layout ---------------------------------------------------------
    def build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        self.refresh_button = ttk.Button(toolbar, text="Refresh", command=self.fetch)
        self.refresh_button.pack(side="left")
        self.status_var = tk.StringVar(value=NO_FETCH_TEXT)
        ttk.Label(toolbar, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=12)

        # The filters as a grid, three equal columns that fit any window width (one long row clipped
        # at the right edge). Row one: what and where it stands (find, status, category). Row two:
        # kind, urgency, owner (type, priority, assignee). Reset and the count close the grid.
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(0, 8))
        for col in range(3):
            grid.columnconfigure(col, weight=1, uniform="filters")
        grid.columnconfigure(3, weight=0)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._populate())
        ttk.Label(grid, text="FIND", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.filter_var).grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(0, 6))
        for slot, (field, caption) in enumerate(FILTER_FIELDS, start=1):  # cell 0 is Find
            row, col = divmod(slot, 3)
            ttk.Label(grid, text=caption.upper(), style="Muted.TLabel").grid(row=row * 2, column=col, sticky="w")
            var = tk.StringVar(value=ALL)
            box = ttk.Combobox(grid, textvariable=var, values=[ALL], state="readonly")
            box.grid(row=row * 2 + 1, column=col, sticky="ew", padx=(0, 12), pady=(0, 6))
            box.bind("<<ComboboxSelected>>", lambda _e: self._populate())
            self.filters[field] = var
            self.filter_boxes[field] = box
        tail = ttk.Frame(grid)
        tail.grid(row=3, column=3, sticky="se", pady=(0, 6))
        ttk.Button(tail, text="Clear filters", command=self.clear_filters).pack(side="left", padx=(0, 10))
        self.count_var = tk.StringVar(value="0 of 0 issues")
        ttk.Label(tail, textvariable=self.count_var, style="Muted.TLabel").pack(side="left")

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=COLUMN_IDS, show="headings", selectmode="browse")
        ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        for column, heading, width, stretch in COLUMNS:
            if column == "comments":
                self.tree.heading(column, text=heading)
            else:
                self.tree.heading(column, text=heading, command=lambda c=column: self.sort_by(c))
            self.tree.column(column, width=width, minwidth=40, stretch=stretch)
        # stripes set only `background`, muted sets only `foreground`: a done row is dim on its stripe
        self.tree.tag_configure("muted", foreground=self.window.theme.palette.muted)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", lambda _e: self.open_selected())
        self.tree.bind("<c>", self._on_key_c)
        self.tree.bind("<Motion>", self._on_motion)

    # -- data -----------------------------------------------------------
    def issues(self) -> list[dict[str, Any]]:
        """The rows of the last good fetch, or ``[]``."""
        result = self.window.jira_live
        if result is None or not result.ok or not isinstance(result.data, dict):
            return []
        return list(result.data.get("issues") or [])

    def fetch(self) -> None:
        """The Refresh button: start ``jira live`` on a worker thread; ``_apply`` paints it when it is in.

        Nothing here waits on Jira. A second call while a fetch runs is ignored (the button is
        disabled meanwhile, but F5, the dashboard tile and ``on_show`` can still arrive).
        """
        if self.fetcher.running:
            return
        self.window.set_status("Fetching Jira …")
        self.status_var.set(FETCHING_TEXT)
        self.refresh_button.state(["disabled"])
        window = self.window
        # The worker runs the verb and nothing else: ``execute_quiet`` touches no widget. The only
        # event the verb publishes is ``jira.live``, whose ``_on_event`` branch returns before any
        # Tk call, and ``jira live`` writes no row, so no refreshing topic can reach the bus from
        # the worker; the automation server runs its verbs on the Tk thread, so this is the one
        # place a verb runs off it.
        self.fetcher.start(lambda: window.execute_quiet("jira", action="live"), name="jira-live-fetch")

    def _apply(self, result: Result) -> None:
        """Tk thread: the Result into ``window.jira_live`` and the status bar, then a repaint.

        A failure after a success keeps the old rows; the status bar reports it as ``run_quiet``
        would have.
        """
        self.refresh_button.state(["!disabled"])
        if result.ok or self.window.jira_live is None:
            self.window.jira_live = result
        self.window.report_quiet("jira", result)
        if result.ok and not result.warnings:
            self.window.set_status(f"Jira: {result.data['count']} issues fetched")
        self.refresh()

    def wait_fetch(self, timeout: float = 5.0) -> Result | None:
        """Test helper: pump the Tk loop until the running fetch has been applied; the Result applied."""
        return self.fetcher.wait(timeout)

    def destroy(self) -> None:
        """A theme pick or a close drops the poll and never waits on the worker."""
        self.fetcher.cancel()
        super().destroy()

    def refresh(self) -> None:
        """Repaint from ``window.jira_live``; never fetches. While a fetch runs the label keeps saying so."""
        result = self.window.jira_live
        if self.fetcher.running:
            self.status_var.set(FETCHING_TEXT)
        elif result is None:
            self.status_var.set(NO_FETCH_TEXT)
        elif not result.ok:
            first = result.errors[0] if result.errors else "unknown error"
            self.status_var.set(f"Offline: {first} · press Refresh")
        else:
            data = result.data
            line = f"{data['count']} issues · fetched {local_clock(data.get('fetched_at'))} · {data['jql']}"
            if data.get("truncated"):
                line += f" · truncated at {data['count']}"
            self.status_var.set(line)
        self._rebuild_filters()
        self._populate()

    def on_show(self) -> None:
        """First show of a session: a fetch only when ``jira_live_autofetch`` is explicitly true, else a repaint."""
        if self.window.jira_live is None and self.brain.config.get("jira_live_autofetch", False) is True:
            self.fetch()
        else:
            self.refresh()

    # -- filters and sorting ---------------------------------------------
    def _rebuild_filters(self) -> None:
        """Combobox values from the rows present; a selection that is gone resets to ``(all)``."""
        rows = self.issues()
        for field, var in self.filters.items():
            present = {r.get(field) for r in rows}
            values = sorted((v for v in present if isinstance(v, str) and v), key=str.casefold)
            if field == "status_category":
                values = [v for v in CATEGORY_ORDER if v in present] + [v for v in values if v not in CATEGORY_ORDER]
            choices = [ALL, *values]
            if None in present or "" in present:
                choices.append(NONE)
            self.filter_boxes[field]["values"] = choices
            if var.get() not in choices:
                var.set(ALL)

    def _visible_rows(self) -> list[dict[str, Any]]:
        rows = self.issues()
        needle = self.filter_var.get().strip().casefold()
        if needle:
            rows = [
                r for r in rows
                if needle in (r.get("key") or "").casefold() or needle in (r.get("summary") or "").casefold()
            ]
        for field, var in self.filters.items():
            choice = var.get()
            if choice == ALL:
                continue
            want = None if choice == NONE else choice
            rows = [r for r in rows if (r.get(field) or None) == want]
        if self.sort_column:
            column = self.sort_column
            present = [r for r in rows if r.get(column) is not None]
            absent = [r for r in rows if r.get(column) is None]  # last in both directions
            rows = sorted(present, key=lambda r: sort_value(column, r), reverse=self.sort_desc) + absent
        return rows

    def _populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        shown = self._visible_rows()
        self._rows_by_key = {}
        for row in shown:
            key = str(row.get("key") or "")
            if not key or self.tree.exists(key):
                continue
            self._rows_by_key[key] = row
            self.tree.insert("", "end", iid=key, values=[cell_text(c, row) for c in COLUMN_IDS])
        self.window.theme.stripe(self.tree)  # replaces every tag tuple: mute afterwards
        for key, row in self._rows_by_key.items():
            if row.get("status_category") == "done":
                self.tree.item(key, tags=(*self.tree.item(key, "tags"), "muted"))
        for column, heading, _, _ in COLUMNS:
            marker = ""
            if column == self.sort_column:
                marker = " ▼" if self.sort_desc else " ▲"
            self.tree.heading(column, text=heading + marker)
        fit_columns(self.tree)  # every column fits its widest cell and heading; Summary still stretches
        self.count_var.set(f"{len(shown)} of {len(self.issues())} issues")

    def sort_by(self, column: str, desc: bool | None = None) -> None:
        if desc is None:
            desc = not self.sort_desc if self.sort_column == column else False
        self.sort_column, self.sort_desc = column, desc
        self._populate()

    def clear_filters(self) -> None:
        """Text box empty, every combobox ``(all)``, server order."""
        self.sort_column, self.sort_desc = None, False
        for var in self.filters.values():
            var.set(ALL)
        if self.filter_var.get():
            self.filter_var.set("")  # the trace repopulates
        else:
            self._populate()

    # -- opening an issue and its comments ---------------------------------
    def open_selected(self) -> None:
        """The focused row's URL to the browser; the status bar when the window is not interactive."""
        key = self.tree.focus()
        row = self._rows_by_key.get(key)
        if row is None:
            self.window.set_status("Select an issue first")
            return
        url = row.get("url")
        if not url:
            self.window.set_status(f"{key} has no URL")
            return
        if self.window.interactive:
            webbrowser.open(url)
        self.window.set_status(f"Open: {url}")

    def _on_click(self, event: Any) -> str | None:
        if self.tree.identify_column(event.x) != COMMENTS_COLUMN:
            return None  # any other column: normal selection
        key = self.tree.identify_row(event.y)
        if key:
            self.window.open_comments(key)
        return "break"

    def _on_double_click(self, event: Any) -> str | None:
        if self.tree.identify_column(event.x) == COMMENTS_COLUMN:
            return "break"  # the first click of the pair already opened the comments
        self.open_selected()
        return None

    def _on_key_c(self, _event: Any) -> None:
        key = self.tree.focus()
        if key:
            self.window.open_comments(key)

    def _on_motion(self, event: Any) -> None:
        over_button = self.tree.identify_column(event.x) == COMMENTS_COLUMN and bool(self.tree.identify_row(event.y))
        cursor = "hand2" if over_button else ""
        if cursor != self._cursor:
            self._cursor = cursor
            self.tree.configure(cursor=cursor)
