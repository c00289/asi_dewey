"""EntityScreen: the generic table-plus-form page produced for every entity from its schema."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..schema import EntitySchema, FieldSpec, FieldType
from .screens import Screen, ScrollableFrame, fit_columns
from .widgets import FieldWidget, WidgetFactory

if TYPE_CHECKING:
    from .main_window import MainWindow

MAX_FLAG_COLUMNS = 8
TRUNCATE = 70


def cell_text(spec: FieldSpec | None, value: Any) -> str:
    if value is None:
        return ""
    if spec is not None and spec.type is FieldType.BOOL:
        return "✓" if value else ""
    text = str(value).replace("\n", " ")
    return text if len(text) <= TRUNCATE else text[: TRUNCATE - 1] + "…"


class EntityScreen(Screen):
    def __init__(self, master: tk.Misc, window: MainWindow, schema: EntitySchema) -> None:
        self.schema = schema
        self.rows: list[dict[str, Any]] = []
        self.by_id: dict[int, dict[str, Any]] = {}
        self.selected_id: int | None = None
        self.sort_key: str | None = None
        self.sort_desc = False
        self.widgets: dict[str, FieldWidget] = {}
        super().__init__(master, window)

    # -- layout ---------------------------------------------------------
    def build(self) -> None:
        flags = [f for f in self.schema.fields if f.is_flag]
        self.columns = ["id"] + [
            f.name for f in self.schema.fields if not f.is_flag or len(flags) <= MAX_FLAG_COLUMNS
        ]

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Search").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._populate())
        ttk.Entry(toolbar, textvariable=self.search_var, width=30).pack(side="left", padx=(4, 12))
        for text, command in (
            ("New", self.new), ("Save", self.save), ("Delete", self.delete),
            ("Duplicate", self.duplicate), ("Refresh", self.refresh),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=2)
        self.count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)

        table = ttk.Frame(paned)
        self.tree = ttk.Treeview(table, columns=self.columns, show="headings", selectmode="browse")
        ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        for name in self.columns:
            spec = None if name == "id" else self.schema.field(name)
            header = "id" if spec is None else spec.header
            self.tree.heading(name, text=header, command=lambda n=name: self.sort_by(n))
            if spec is None or spec.type is FieldType.INT:
                width = 60
            elif spec.is_flag:
                width = 50
            elif spec.type in (FieldType.MULTILINE, FieldType.URL):
                width = 320
            elif spec.type is FieldType.DATE:
                width = 100
            else:
                width = 180
            stretch = spec is not None and spec.type is FieldType.MULTILINE
            self.tree.column(name, width=width, minwidth=40, stretch=stretch)  # fit_columns has the last word
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(table, weight=3)

        form_box = ttk.LabelFrame(paned, text=f"{self.schema.label} details")
        self.form = ScrollableFrame(form_box)
        self.form.pack(fill="both", expand=True)
        self._build_form(self.form.inner)
        paned.add(form_box, weight=2)

    def _build_form(self, parent: ttk.Frame) -> None:
        factory = WidgetFactory(self.brain.lookups)
        parent.columnconfigure(1, weight=1)
        row = 0
        for spec in self.schema.fields:
            if spec.group:
                continue
            ttk.Label(parent, text=spec.header + (" *" if spec.required else "")).grid(
                row=row, column=0, sticky="ne", padx=(4, 8), pady=3
            )
            widget = factory.create(parent, spec)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self.widgets[spec.name] = widget
            row += 1
        for group, specs in self.schema.groups().items():
            if not group:
                continue
            box = ttk.LabelFrame(parent, text=group.capitalize())
            box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=6)
            grid_row = 0
            flag_col = 0
            for spec in specs:
                if spec.is_flag:
                    widget = factory.create(box, spec)
                    widget.grid(row=grid_row, column=flag_col, sticky="w", padx=4, pady=1)
                    flag_col += 1
                    if flag_col == 3:
                        flag_col = 0
                        grid_row += 1
                else:
                    if flag_col:
                        grid_row += 1
                        flag_col = 0
                    ttk.Label(box, text=spec.header).grid(row=grid_row, column=0, sticky="w", padx=4, pady=2)
                    widget = factory.create(box, spec)
                    widget.grid(row=grid_row, column=1, columnspan=2, sticky="ew", pady=2)
                    grid_row += 1
                self.widgets[spec.name] = widget
            row += 1

    # -- data -----------------------------------------------------------
    def refresh(self) -> None:
        result = self.brain.execute("list", entity=self.schema.name, actor="gui")
        if not result.ok:
            self.window.notify_error("Could not load rows", "; ".join(result.errors))
            return
        self.rows = result.data
        self.by_id = {r["id"]: r for r in self.rows}
        if self.selected_id not in self.by_id:
            self.selected_id = None
        self._populate()

    def _visible_rows(self) -> list[dict[str, Any]]:
        needle = self.search_var.get().strip().casefold()
        rows = self.rows
        if needle:
            rows = [r for r in rows if any(needle in str(v).casefold() for v in r.values() if v not in (None, ""))]
        if self.sort_key:
            key = self.sort_key

            def sort_value(r: dict[str, Any]) -> tuple[int, Any]:
                v = r.get(key)
                if v is None:
                    return (1, 0)
                return (0, v.casefold() if isinstance(v, str) else v)

            rows = sorted(rows, key=sort_value, reverse=self.sort_desc)
        return rows

    def _populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        shown = self._visible_rows()
        for r in shown:
            values = [cell_text(None if c == "id" else self.schema.field(c), r.get(c)) for c in self.columns]
            self.tree.insert("", "end", iid=str(r["id"]), values=values)
        self.window.theme.stripe(self.tree)
        fit_columns(self.tree, self._lookup_values())
        self.count_var.set(f"{len(shown)} of {len(self.rows)} rows")
        if self.selected_id is not None and self.tree.exists(str(self.selected_id)):
            self.tree.selection_set(str(self.selected_id))

    def _lookup_values(self) -> dict[str, tuple[str, ...]]:
        """Every ENUM column's allowed values (the source ``EnumWidget`` offers): the column fits
        the longest even when no row holds it. The cell text of the other types is in the tree."""
        return {
            spec.name: self.brain.lookups.get(spec.lookup or "", ())
            for spec in self.schema.fields
            if spec.type is FieldType.ENUM and spec.name in self.columns
        }

    def sort_by(self, column: str, desc: bool | None = None) -> None:
        if desc is None:
            desc = not self.sort_desc if self.sort_key == column else False
        self.sort_key, self.sort_desc = column, desc
        self._populate()

    def select(self, row_id: int) -> None:
        if self.tree.exists(str(row_id)):
            self.tree.selection_set(str(row_id))
            self.tree.see(str(row_id))
        self._load(row_id)

    def _on_select(self, _event: tk.Event | None = None) -> None:
        selection = self.tree.selection()
        if selection:
            self._load(int(selection[0]))

    def _load(self, row_id: int) -> None:
        row = self.by_id.get(row_id)
        if row is None:
            return
        self.selected_id = row_id
        for name, widget in self.widgets.items():
            widget.set(row.get(name))
        self.window.set_status(f"{self.schema.label} {row_id} selected")

    def form_data(self) -> dict[str, Any]:
        return {name: widget.get() for name, widget in self.widgets.items()}

    # -- actions --------------------------------------------------------
    def new(self) -> None:
        self.selected_id = None
        self.tree.selection_remove(*self.tree.selection())
        for widget in self.widgets.values():
            widget.clear()
        if self.widgets:
            next(iter(self.widgets.values())).focus_field()
        self.window.set_status(f"New {self.schema.label.lower()}: fill the form and press Save (Ctrl+S)")

    def save(self) -> None:
        data = self.form_data()
        if self.selected_id is None:
            result = self.window.run("create", entity=self.schema.name, data=data)
        else:
            result = self.window.run("update", entity=self.schema.name, id=self.selected_id, data=data)
        if not result.ok:
            return
        self.selected_id = result.data["id"]
        self.refresh()
        self.select(self.selected_id)
        note = f"Saved {self.schema.label.lower()} {self.selected_id}"
        if result.warnings:
            note += " (" + "; ".join(result.warnings) + ")"
        self.window.set_status(note)

    def delete(self) -> None:
        if self.selected_id is None:
            self.window.set_status("Select a row to delete")
            return
        row_id = self.selected_id
        if not self.window.confirm("Delete", f"Delete {self.schema.label.lower()} {row_id}?"):
            return
        result = self.window.run("delete", entity=self.schema.name, id=row_id)
        if result.ok:
            self.new()
            self.refresh()
            self.window.set_status(f"Deleted {self.schema.label.lower()} {row_id}")

    def duplicate(self) -> None:
        if self.selected_id is None:
            self.window.set_status("Select a row to duplicate")
            return
        self.selected_id = None
        self.tree.selection_remove(*self.tree.selection())
        if "order" in self.widgets:
            self.widgets["order"].clear()
        self.window.set_status("Duplicating: edit the form and press Save to create the copy")
