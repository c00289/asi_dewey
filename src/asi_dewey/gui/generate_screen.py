"""GenerateScreen: build catalog diagrams and documents from the window.

The screen is a client of the command path like every other screen: it calls
``window.run("diagram", ...)`` and ``window.run("document", ...)`` and nothing else. The
catalogs it lists come from the same verbs called without a name.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ..commands import Result
from .screens import Screen

KINDS = ("diagram", "document")


class GenerateScreen(Screen):
    def build(self) -> None:
        self.catalog: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
        self.selected: tuple[str, str] | None = None  # (kind, key)
        self.param_vars: dict[str, tk.StringVar] = {}
        self.last_result: Result | None = None
        self.last_primary: str | None = None

        folder = ttk.LabelFrame(self, text="Output folder (generated files are views of the database)")
        folder.pack(fill="x", pady=(0, 8))
        ttk.Label(folder, text="Folder").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.out_var = tk.StringVar(value=self.brain.out_dir)
        ttk.Entry(folder, textvariable=self.out_var, width=70).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(folder, text="Browse…", command=self._browse).grid(row=0, column=2, padx=4)
        folder.columnconfigure(1, weight=1)

        lists = ttk.Frame(self)
        lists.pack(fill="x", pady=(0, 8))
        self.lists: dict[str, tk.Listbox] = {}
        for column, (kind, title) in enumerate((("diagram", "Diagrams"), ("document", "Documents"))):
            box = ttk.LabelFrame(lists, text=title)
            box.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
            listbox = tk.Listbox(box, exportselection=False, activestyle="none", height=6, font=self.window.theme.ui)
            listbox.pack(fill="both", expand=True, padx=6, pady=6)
            listbox.bind("<<ListboxSelect>>", lambda e, k=kind: self._on_pick(k))
            self.lists[kind] = listbox
            lists.columnconfigure(column, weight=1)
        self.description_var = tk.StringVar(value="Select a diagram or a document.")
        ttk.Label(self, textvariable=self.description_var, wraplength=900, justify="left", style="Muted.TLabel").pack(
            fill="x", pady=(0, 8)
        )

        self.params_box = ttk.LabelFrame(self, text="Parameters")
        self.params_box.pack(fill="x", pady=(0, 8))
        self.params_inner = ttk.Frame(self.params_box)
        self.params_inner.pack(fill="x", padx=6, pady=4)
        self._build_param_form(None)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(0, 8))
        self.build_button = ttk.Button(buttons, text="Build", command=self.build_selected)
        self.build_button.pack(side="left", padx=(0, 6))
        self.open_file_button = ttk.Button(buttons, text="Open file", command=self.open_file, state="disabled")
        self.open_file_button.pack(side="left", padx=(0, 6))
        self.open_folder_button = ttk.Button(buttons, text="Open folder", command=self.open_folder, state="disabled")
        self.open_folder_button.pack(side="left")

        log_box = ttk.LabelFrame(self, text="Log")
        log_box.pack(fill="both", expand=True)
        self.log = tk.Text(log_box, height=10, wrap="word", state="disabled")
        bar = ttk.Scrollbar(log_box, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        self.log.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

    # -- catalog --------------------------------------------------------
    def refresh(self) -> None:
        for kind in KINDS:
            result = self.brain.execute(kind, actor="gui")
            self.catalog[kind] = list((result.data or {}).get("catalog", [])) if result.ok else []
            listbox = self.lists[kind]
            listbox.delete(0, "end")
            for spec in self.catalog[kind]:
                listbox.insert("end", f"  {spec['title']}")
        if self.selected is not None:
            kind, key = self.selected
            if self.spec(kind, key) is None:
                self.selected = None
                self._build_param_form(None)
            else:
                self._highlight(kind, key)

    def spec(self, kind: str, key: str) -> dict[str, Any] | None:
        return next((s for s in self.catalog.get(kind, []) if s["key"] == key), None)

    def select(self, kind: str, key: str) -> dict[str, Any]:
        """Select a catalog entry (``kind`` is ``diagram`` or ``document``); builds its parameter form."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        spec = self.spec(kind, key)
        if spec is None:
            raise KeyError(f"unknown {kind} {key!r}")
        self.selected = (kind, key)
        self._highlight(kind, key)
        self.description_var.set(f"{spec['title']} ({kind} {key}): {spec['description']}")
        self._build_param_form(spec)
        return spec

    def _highlight(self, kind: str, key: str) -> None:
        for other in KINDS:
            self.lists[other].selection_clear(0, "end")
        index = next((i for i, s in enumerate(self.catalog[kind]) if s["key"] == key), None)
        if index is not None:
            self.lists[kind].selection_set(index)
            self.lists[kind].see(index)

    def _on_pick(self, kind: str) -> None:
        picked = self.lists[kind].curselection()
        if picked:
            self.select(kind, self.catalog[kind][picked[0]]["key"])

    def _build_param_form(self, spec: dict[str, Any] | None) -> None:
        for child in self.params_inner.winfo_children():
            child.destroy()
        self.param_vars = {}
        params = (spec or {}).get("params", [])
        if not params:
            ttk.Label(self.params_inner, text="No parameters.", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
            return
        for row, param in enumerate(params):
            label = param["name"] + (" *" if param.get("required") else "")
            ttk.Label(self.params_inner, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            var = tk.StringVar(value=param.get("default") or "")
            lookup = param.get("lookup")
            if lookup:
                values = list(self.brain.lookups.get(lookup, ()))
                widget: tk.Widget = ttk.Combobox(self.params_inner, textvariable=var, values=values, width=44)
            else:
                widget = ttk.Entry(self.params_inner, textvariable=var, width=46)
            widget.grid(row=row, column=1, sticky="w", pady=2)
            help_text = ttk.Label(self.params_inner, text=param.get("help", ""), style="Muted.TLabel")
            help_text.grid(row=row, column=2, sticky="w", padx=8)
            self.param_vars[param["name"]] = var

    def params(self) -> dict[str, str]:
        return {name: var.get().strip() for name, var in self.param_vars.items() if var.get().strip()}

    def focus_documents(self) -> None:
        """Used by File > Build document…: show the Documents list with the first entry selected."""
        if self.catalog["document"] and (self.selected is None or self.selected[0] != "document"):
            self.select("document", self.catalog["document"][0]["key"])
        self.lists["document"].focus_set()

    # -- actions --------------------------------------------------------
    def build_selected(self) -> Result:
        if self.selected is None:
            self.window.set_status("Select a diagram or a document to build")
            return Result.failure("nothing selected")
        kind, key = self.selected
        out = self.out_var.get().strip() or None
        self.window.set_status(f"Building {kind} {key} …")
        self.window.configure(cursor="watch")
        self.window.update_idletasks()
        try:
            result = self.window.run(kind, name=key, out=out, param=self.params())
        finally:
            self.window.configure(cursor="")
        self.last_result = result
        if result.ok:
            data = result.data or {}
            self.last_primary = data.get("primary")
            self._append(f"[ok] {kind} {key} -> {self.last_primary}")
            for extra in sorted(set((data.get("paths") or {}).values()) - {self.last_primary}):
                self._append(f"     {extra}")
            for figure in data.get("diagrams") or []:
                self._append(f"     figure: {figure.get('png', figure.get('name'))}")
            for warning in result.warnings:
                self._append(f"     warning: {warning}")
            self.open_file_button.configure(state="normal")
            self.open_folder_button.configure(state="normal")
            note = f"Built {kind} {key}: {self.last_primary}"
            if data.get("pages"):
                note += f" ({data['pages']} pages)"
            self.window.set_status(note)
        else:
            self._append(f"[failed] {kind} {key}: " + "; ".join(result.errors))
        return result

    def open_file(self) -> None:
        if self.last_primary:
            self._open_path(self.last_primary)

    def open_folder(self) -> None:
        if self.last_primary:
            self._open_path(str(Path(self.last_primary).parent))

    def _open_path(self, path: str) -> None:
        if self.window.interactive and hasattr(os, "startfile"):  # Windows; elsewhere the log shows the path
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            self._append(f"open: {path}")
        self.window.set_status(path)

    def _browse(self) -> None:
        path = filedialog.askdirectory(parent=self, initialdir=self.out_var.get() or None, title="Output folder")
        if path:
            self.out_var.set(path)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
