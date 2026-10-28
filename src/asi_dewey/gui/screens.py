"""Screen base class, ScreenFactory, the ScrollableFrame and WorkerFetch helpers and ``fit_columns``."""

from __future__ import annotations

import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable, Mapping
from tkinter import ttk
from typing import TYPE_CHECKING, ClassVar

from ..commands import Result
from ..errors import NotFound

if TYPE_CHECKING:
    from ..brain import Brain
    from .main_window import MainWindow


class Screen(ttk.Frame):
    """One page in the main window. Subclasses override ``build`` and ``refresh``."""

    key: ClassVar[str] = ""
    title: ClassVar[str] = ""

    def __init__(self, master: tk.Misc, window: MainWindow) -> None:
        super().__init__(master, padding=8)
        self.window = window
        self.brain: Brain = window.brain
        self.build()

    def build(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def on_show(self) -> None:
        self.refresh()


class ScrollableFrame(ttk.Frame):
    """A frame with a vertical scrollbar; put children in ``.inner``."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


POLL_MS = 100  # how often the Tk thread looks for a worker's Result


class WorkerFetch:
    """One verb on a daemon worker thread, its Result applied on the Tk thread.

    ``start(run)`` runs ``run()`` (a ``MainWindow.execute_quiet`` call: no Tk inside it) on a
    daemon thread and polls it with ``widget.after`` every ``POLL_MS``; once the thread is done,
    ``apply(result)`` runs on the Tk thread, unless the widget is gone by then. Nothing ever joins
    the worker: ``cancel()`` (from the widget's ``destroy``) only drops the poll, and a late Result
    is dropped with it, so a theme pick or a close never waits on Jira. ``wait()`` is the test
    helper that pumps the Tk loop until the Result has been applied.
    """

    def __init__(self, widget: tk.Misc, apply: Callable[[Result], None]) -> None:
        self.widget = widget
        self.apply = apply
        self.thread: threading.Thread | None = None
        self.last: Result | None = None  # the last Result a worker produced, applied or dropped
        self._job: str | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None

    def start(self, run: Callable[[], Result], name: str = "fetch") -> bool:
        """Start ``run`` on a worker; ``False`` (and nothing started) while one is still running."""
        if self.thread is not None:
            return False
        self.thread = threading.Thread(target=self._work, args=(run,), name=name, daemon=True)
        self.thread.start()
        self._job = self.widget.after(POLL_MS, self._poll)  # never applied inside ``start``, even for an instant verb
        return True

    def _work(self, run: Callable[[], Result]) -> None:
        """The worker thread: the verb and nothing else; ``last`` is its only output."""
        try:
            self.last = run()
        except BaseException as exc:  # a Brain verb always answers with a Result; a stub might not
            self.last = Result.failure(f"{type(exc).__name__}: {exc}")

    def _poll(self) -> None:
        """Tk thread only."""
        self._job = None
        thread = self.thread
        if thread is None:
            return
        if thread.is_alive():
            self._job = self.widget.after(POLL_MS, self._poll)
            return
        self.thread = None
        result = self.last if self.last is not None else Result.failure(f"{thread.name} ended without a Result")
        if self.widget.winfo_exists():
            self.apply(result)

    def cancel(self) -> None:
        """Drop the poll; the worker runs on to its end and its Result is never applied."""
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None

    def wait(self, timeout: float = 5.0) -> Result | None:
        """Test helper: pump ``update()`` until the running fetch has been applied; the last Result."""
        deadline = time.monotonic() + timeout
        while self.thread is not None:
            if time.monotonic() > deadline:
                raise TimeoutError(f"{self.thread.name} did not finish within {timeout} s")
            self.widget.update()
            time.sleep(0.01)
        return self.last


def fit_columns(
    tree: ttk.Treeview,
    extra: Mapping[str, Iterable[str]] | None = None,
    *,
    min_width: int = 40,
    max_width: int = 600,
    padding: int = 24,
) -> dict[str, int]:
    """Size every column of ``tree`` to its widest text, so nothing is clipped.

    The candidates of a column are its heading (measured with the ``Treeview.Heading`` font),
    every cell currently in the tree and ``extra[column]`` (both with the ``Treeview`` font):
    ``extra`` is the rest of the column's domain, such as every value of an enum's lookup, so
    the column fits the longest allowed value even when no row holds it. Width is
    ``clamp(widest + padding, min_width, max_width)``, and it is also the column's ``minwidth`` with
    ``stretch`` off: Tk shrinks a stretchable column towards its minimum whenever the fitted total
    exceeds the widget, which would clip the one column that most needs its width.
    Measuring needs fonts, not a mapped widget, so a withdrawn window fits the same.
    """
    style = ttk.Style(tree)
    cell_font = tkfont.Font(tree, font=style.lookup("Treeview", "font") or "TkDefaultFont")
    heading_font = tkfont.Font(tree, font=style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    items = tree.get_children("")
    widths: dict[str, int] = {}
    for column in tree.tk.splitlist(tree["columns"]):
        widest = heading_font.measure(str(tree.heading(column, "text")))
        for iid in items:
            widest = max(widest, cell_font.measure(str(tree.set(iid, column))))
        for text in (extra or {}).get(column, ()):
            widest = max(widest, cell_font.measure(str(text)))
        width = max(min_width, min(max_width, widest + padding))
        tree.column(column, width=width, minwidth=width, stretch=False)
        widths[column] = width
    return widths


ScreenBuilder = Callable[[tk.Misc, "MainWindow"], Screen]


class ScreenFactory:
    """Key -> (title, builder). The navigation list is built from this."""

    def __init__(self) -> None:
        self._builders: dict[str, tuple[str, ScreenBuilder]] = {}

    def register(self, key: str, title: str, builder: ScreenBuilder) -> None:
        if key in self._builders:
            raise ValueError(f"screen {key!r} already registered")
        self._builders[key] = (title, builder)

    def create(self, key: str, master: tk.Misc, window: MainWindow) -> Screen:
        try:
            title, builder = self._builders[key]
        except KeyError:
            raise NotFound(f"unknown screen {key!r}; known: {', '.join(self._builders)}") from None
        screen = builder(master, window)
        screen.key = key
        screen.title = title
        return screen

    def items(self) -> list[tuple[str, str]]:
        return [(key, title) for key, (title, _) in self._builders.items()]

    def title(self, key: str) -> str:
        return self._builders[key][0]

    def __contains__(self, key: object) -> bool:
        return key in self._builders


# Entities that keep a table, commands, a workbook sheet and dump/load but have no window.
# jira_ticket: a cache fed by `jira sync`; the live view is the `jira_live` screen (0.5.0).
# safety_plan_row: the Safety Plan is Kletz's since the 2026-10-27 split.
HIDDEN_ENTITY_SCREENS: frozenset[str] = frozenset({"jira_ticket", "safety_plan_row"})


def build_default_screens(brain: Brain, hidden: frozenset[str] = HIDDEN_ENTITY_SCREENS) -> ScreenFactory:
    """Dashboard, JIRA Live Data, one entity screen per entity not in ``hidden``, Export / Import, Generate."""
    from .dashboard import DashboardScreen
    from .entity_screen import EntityScreen
    from .generate_screen import GenerateScreen
    from .jira_live_screen import JiraLiveScreen
    from .transfer_screen import TransferScreen

    unknown = hidden - set(brain.registry.names())
    if unknown:
        raise ValueError(f"HIDDEN_ENTITY_SCREENS names unknown entities: {', '.join(sorted(unknown))}")
    factory = ScreenFactory()
    factory.register("dashboard", "Dashboard", DashboardScreen)
    factory.register("jira_live", "JIRA Live Data", JiraLiveScreen)  # second in nav and View, as in asi_kletz
    for schema in brain.registry:
        if schema.name in hidden:
            continue
        factory.register(
            f"entity:{schema.name}", schema.sheet,
            lambda master, window, s=schema: EntityScreen(master, window, s),
        )
    factory.register("transfer", "Export / Import", TransferScreen)
    factory.register("generate", "Generate", GenerateScreen)
    return factory
