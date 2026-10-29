"""DashboardScreen: counts per entity, open Jira tickets, tasks due soon, recent changes."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..services.control_structure_service import PART_ENTITIES
from ..services.queries import DUE_WINDOW_DAYS, open_jira_tickets, recent_changes, tasks_due
from ..services.stpa_service import PART_ENTITIES as STPA_PART_ENTITIES
from .screens import Screen, fit_columns
from .theme import GridBanner

# the parts of a control structure or of an STPA analysis have no tile of their own: the structure's
# (the analysis's) tile counts the structures (the analyses), the parts are counted under it by the
# Control structures (phase 3) and STPA analyses screens
UNTILED: frozenset[str] = frozenset(PART_ENTITIES) | frozenset(STPA_PART_ENTITIES)


class DashboardScreen(Screen):
    def build(self) -> None:
        banner = GridBanner(self, self.window.theme, "SYSTEM OVERVIEW", "WHEEL LOADER // FUNCTIONAL SAFETY")
        banner.pack(fill="x", pady=(0, 8))
        self.tiles = ttk.LabelFrame(self, text="Rows per entity (click to open)")
        self.tiles.pack(fill="x", pady=(0, 8))
        self._tile_vars: dict[str, tk.StringVar] = {}
        tiled = [schema for schema in self.brain.registry if schema.name not in UNTILED]
        for index, schema in enumerate(tiled):
            var = tk.StringVar(value="0")
            self._tile_vars[schema.name] = var
            tile = ttk.Frame(self.tiles, padding=8, style="Tile.TFrame")
            tile.grid(row=index // 5, column=index % 5, padx=4, pady=4, sticky="nsew")
            ttk.Label(tile, textvariable=var, style="TileCount.TLabel").pack()
            ttk.Label(tile, text=schema.sheet.upper(), style="TileName.TLabel").pack()
            key = f"entity:{schema.name}"
            if key not in self.window.factory:
                continue  # counted but not clickable: the entity has no screen (HIDDEN_ENTITY_SCREENS)
            for widget in (tile, *tile.winfo_children()):
                widget.bind("<Button-1>", lambda e, k=key: self.window.show(k))
                widget.bind("<Enter>", lambda e, t=tile: t.configure(style="TileHover.TFrame"))
                widget.bind("<Leave>", lambda e, t=tile: t.configure(style="Tile.TFrame"))
        for col in range(5):
            self.tiles.columnconfigure(col, weight=1)

        lower = ttk.PanedWindow(self, orient="horizontal")
        lower.pack(fill="both", expand=True)
        # no table shows an id or an order column (docs/hidden-identity-plan.md, 3.3); the audit
        # table keeps entity_id, which is the trace of a change, not a vestige
        self.jira = self._table(lower, "Open Jira tickets", ("name", "url"), (360, 300))
        self.tasks = self._table(
            lower, f"Tasks ending within {DUE_WINDOW_DAYS} days", ("name", "end", "task_class"), (300, 90, 110)
        )
        self.audit = self._table(
            lower, "Recent changes", ("ts", "actor", "action", "entity", "entity_id"), (140, 70, 90, 110, 60)
        )

    def _table(
        self, parent: ttk.PanedWindow, title: str, columns: tuple[str, ...], widths: tuple[int, ...]
    ) -> ttk.Treeview:
        box = ttk.LabelFrame(parent, text=title)
        tree = ttk.Treeview(box, columns=columns, show="headings", height=12)
        for column, width in zip(columns, widths, strict=True):
            tree.heading(column, text=column.replace("_", " "))
            tree.column(column, width=width, minwidth=40)  # a starting width; fit_columns after each _fill
        bar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        parent.add(box, weight=1)
        return tree

    def _fill(self, tree: ttk.Treeview, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=[("" if row.get(c) is None else str(row.get(c))) for c in columns])
        self.window.theme.stripe(tree)
        fit_columns(tree)

    def refresh(self) -> None:
        status = self.brain.status()
        for name, count in status["entities"].items():
            if name in self._tile_vars:
                self._tile_vars[name].set(str(count))
        # the same queries feed the status_report document (services/queries.py)
        self._fill(self.jira, open_jira_tickets(self.brain), ("name", "url"))
        self._fill(self.tasks, tasks_due(self.brain), ("name", "end", "task_class"))
        self._fill(self.audit, recent_changes(self.brain, 25), ("ts", "actor", "action", "entity", "entity_id"))
        self.window.set_status(f"Database: {self.brain.db_path}")
