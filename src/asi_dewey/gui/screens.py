"""Screen base class, ScreenFactory, the ScrollableFrame helper and ``fit_columns``."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable, Mapping
from tkinter import ttk
from typing import TYPE_CHECKING, ClassVar

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
# jira_ticket: a cache fed by `jira sync`, read on the Dashboard and through the verbs (the JIRA Live
# Data screen of 0.5.0 was removed in 0.8.1 by owner decision; the `jira` verbs stay).
# safety_plan_row: the Safety Plan is Kletz's since the 2026-10-27 split.
# The Control structures and STPA analyses screens of 0.10.0, with their thirteen entities, are asi_kletz's
# since 0.11.0 (the owner, 2026-10-29: "move everything to Kletz"); `handover` is what remains of them here.
HIDDEN_ENTITY_SCREENS: frozenset[str] = frozenset({"jira_ticket", "safety_plan_row"})


def build_default_screens(brain: Brain, hidden: frozenset[str] = HIDDEN_ENTITY_SCREENS) -> ScreenFactory:
    """Dashboard, one entity screen per entity not in ``hidden``, Export / Import, Generate."""
    from .dashboard import DashboardScreen
    from .entity_screen import EntityScreen
    from .generate_screen import GenerateScreen
    from .transfer_screen import TransferScreen

    unknown = hidden - set(brain.registry.names())
    if unknown:
        raise ValueError(f"HIDDEN_ENTITY_SCREENS names unknown entities: {', '.join(sorted(unknown))}")
    factory = ScreenFactory()
    factory.register("dashboard", "Dashboard", DashboardScreen)
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
