"""TransferScreen: export/import the workbook and dump/load JSON, with a result log."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from ..commands import Result
from ..services import LOAD_MODES
from .screens import Screen


class TransferScreen(Screen):
    def build(self) -> None:
        book = ttk.LabelFrame(self, text="Excel workbook (a generated view of the database)")
        book.pack(fill="x", pady=(0, 8))
        ttk.Label(book, text="Workbook").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.workbook_var = tk.StringVar(value=self.brain.workbook_path)
        ttk.Entry(book, textvariable=self.workbook_var, width=70).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(book, text="Browse…", command=self._browse_workbook).grid(row=0, column=2, padx=4)
        ttk.Label(book, text="Import mode").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.mode_var = tk.StringVar(value="replace")
        ttk.Combobox(book, textvariable=self.mode_var, values=list(LOAD_MODES), state="readonly", width=10).grid(
            row=1, column=1, sticky="w"
        )
        buttons = ttk.Frame(book)
        buttons.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 6))
        ttk.Button(buttons, text="Export workbook  (Ctrl+E)", command=self.export_workbook).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="Import workbook", command=self.import_workbook).pack(side="left")
        book.columnconfigure(1, weight=1)

        js = ttk.LabelFrame(self, text="JSON (portable dump for diffing, versioning, and AI tools)")
        js.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(js)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Button(row, text="Dump JSON…", command=self.dump_json).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Load JSON…", command=self.load_json).pack(side="left", padx=(0, 12))
        ttk.Label(row, text="Load mode").pack(side="left")
        self.json_mode_var = tk.StringVar(value="merge")
        ttk.Combobox(row, textvariable=self.json_mode_var, values=list(LOAD_MODES), state="readonly", width=10).pack(
            side="left", padx=4
        )

        log_box = ttk.LabelFrame(self, text="Log")
        log_box.pack(fill="both", expand=True)
        self.log = tk.Text(log_box, height=12, wrap="word", state="disabled")
        bar = ttk.Scrollbar(log_box, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        self.log.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

    # -- helpers --------------------------------------------------------
    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _report(self, result: Result) -> Result:
        if result.ok:
            data = result.data or {}
            counts = ", ".join(
                f"{k}={v if isinstance(v, int) else v.get('inserted', v)}"
                for k, v in (data.get("entities") or {}).items()
            )
            self._append(f"[ok] {result.verb} -> {data.get('path', '')}  {counts}")
            for warning in result.warnings:
                self._append(f"     warning: {warning}")
        else:
            self._append(f"[failed] {result.verb}: " + "; ".join(result.errors))
        return result

    def _browse_workbook(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=Path(self.workbook_var.get()).name, title="Workbook location",
        )
        if path:
            self.workbook_var.set(path)

    # -- actions --------------------------------------------------------
    def export_workbook(self, path: str | Path | None = None) -> Result:
        target = str(path or self.workbook_var.get() or self.brain.workbook_path)
        return self._report(self.window.run("export", format="excel", out=target))

    def import_workbook(self, path: str | Path | None = None, mode: str | None = None) -> Result:
        source = str(path or self.workbook_var.get())
        mode = mode or self.mode_var.get()
        if path is None and not self.window.confirm(
            "Import workbook", f"Import {Path(source).name} with mode '{mode}'?\n\n'replace' wipes every table first."
        ):
            return Result.failure("cancelled", verb="import")
        return self._report(self.window.run("import", format="excel", path=source, mode=mode))

    def dump_json(self, path: str | Path | None = None) -> Result:
        if path is None:
            if not self.window.interactive:
                return Result.failure("no path given", verb="dump")
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="dewey.json",
            )
            if not path:
                return Result.failure("cancelled", verb="dump")
        return self._report(self.window.run("dump", out=str(path)))

    def load_json(self, path: str | Path | None = None, mode: str | None = None) -> Result:
        if path is None:
            if not self.window.interactive:
                return Result.failure("no path given", verb="load")
            path = filedialog.askopenfilename(parent=self, filetypes=[("JSON", "*.json")])
            if not path:
                return Result.failure("cancelled", verb="load")
        return self._report(self.window.run("load", path=str(path), mode=mode or self.json_mode_var.get()))
