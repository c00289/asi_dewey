"""JiraCommentsWindow: one Toplevel per ticket listing its comment history, newest at the top.

Fed by ``jira comments <key>`` run on a worker thread through ``MainWindow.execute_quiet``
(``WorkerFetch``: the window never blocks on Jira); constructed only by
``MainWindow.open_comments``. ``Theme.paint`` paints the root and the option database, so this
window sets its own background; its ttk children take the styles and its ``tk.Text`` bodies take
the ``*Text.*`` option entries. On a theme pick the window is destroyed with the rest of the
root's children (the content is one verb away); it closes with the main window.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..commands import Result
from .jira_live_screen import local_clock
from .screens import ScrollableFrame, WorkerFetch

if TYPE_CHECKING:
    from .main_window import MainWindow

SIZE = "640x520"
MAX_BODY_LINES = 12
FETCHING_TEXT = "Fetching comments …"


def stamp(value: str | None) -> str:
    """Jira's timestamp -> ``YYYY-MM-DD HH:MM``, no zone conversion: a comment's time is Jira's."""
    return (value or "")[:16].replace("T", " ")


class JiraCommentsWindow(tk.Toplevel):
    def __init__(self, window: MainWindow, key: str) -> None:
        super().__init__(window)
        self.window = window
        self.key = key
        self.title(f"{key} — Comments")
        self.geometry(SIZE)
        self.resizable(True, True)
        self.configure(background=window.theme.palette.bg)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<F5>", lambda _e: self.fetch())
        self.url: str | None = None
        self.summary_var = tk.StringVar(value=key)
        self.issue_status_var = tk.StringVar(value="")
        self.url_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.fetcher = WorkerFetch(self, self._apply)
        self._build()

    def _build(self) -> None:
        palette = self.window.theme.palette
        header = ttk.Frame(self, padding=(10, 8))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.summary_var, style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.issue_status_var, style="Muted.TLabel").pack(side="left", padx=12)
        link = ttk.Label(header, textvariable=self.url_var, foreground=palette.accent, cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda _e: self.open_url())

        toolbar = ttk.Frame(self, padding=(10, 0, 10, 6))
        toolbar.pack(fill="x")
        self.refresh_button = ttk.Button(toolbar, text="Refresh", command=self.fetch)
        self.refresh_button.pack(side="left")
        ttk.Button(toolbar, text="Close", command=self.close).pack(side="left", padx=4)
        ttk.Label(toolbar, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=12)

        self.body = ScrollableFrame(self)
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # -- data -----------------------------------------------------------
    def fetch(self) -> None:
        """Start ``jira comments`` on a worker thread; ``_apply`` paints it. A second call while one runs is ignored."""
        if self.fetcher.running:
            return
        self.status_var.set(FETCHING_TEXT)
        self.refresh_button.state(["disabled"])
        window, key = self.window, self.key
        # The worker runs the verb only: ``execute_quiet`` touches no widget, and ``jira comments``
        # publishes nothing and writes nothing, so nothing reaches Tk from that thread.
        self.fetcher.start(
            lambda: window.execute_quiet("jira", action="comments", key=key), name=f"jira-comments-{key}"
        )

    def _apply(self, result: Result) -> None:
        """Tk thread: a failure keeps what is listed and leaves the window open; the status bar reports it."""
        self.refresh_button.state(["!disabled"])
        self.window.report_quiet("jira", result)
        if result.ok:
            self._fill(result.data)
        else:
            self.status_var.set("Error: " + (result.errors[0] if result.errors else "unknown error"))

    def wait_fetch(self, timeout: float = 5.0) -> Result | None:
        """Test helper: pump the Tk loop until the running fetch has been applied; the Result applied."""
        return self.fetcher.wait(timeout)

    def destroy(self) -> None:
        """Close or a theme pick drops the poll and never waits on the worker."""
        self.fetcher.cancel()
        super().destroy()

    def _fill(self, data: dict[str, Any]) -> None:
        self.url = data.get("url") or None
        self.summary_var.set(f"{data.get('key') or self.key}  {data.get('summary') or ''}".rstrip())
        self.issue_status_var.set(data.get("status") or "")
        self.url_var.set(self.url or "")
        for child in self.body.inner.winfo_children():
            child.destroy()
        comments = list(data.get("comments") or [])
        if not comments:
            ttk.Label(self.body.inner, text="No comments.", style="Muted.TLabel").pack(anchor="w", pady=6)
        for comment in comments:
            meta = f"{comment.get('author') or ''} · {stamp(comment.get('created'))}"
            updated = comment.get("updated")
            if updated and updated != comment.get("created"):
                meta += f" · edited {stamp(updated)}"
            ttk.Label(self.body.inner, text=meta, style="Muted.TLabel").pack(anchor="w", pady=(8, 2))
            body = comment.get("body") or ""
            lines = max(1, body.count("\n") + 1)
            text = tk.Text(self.body.inner, wrap="word", height=min(lines, MAX_BODY_LINES), padx=6)
            text.insert("1.0", body)
            text.configure(state="disabled")
            text.pack(fill="x")
            ttk.Frame(self.body.inner, height=1, style="Rule.TFrame").pack(fill="x", pady=(6, 0))
        count = data.get("count", len(comments))
        self.status_var.set(f"{count} comments · fetched {local_clock(data.get('fetched_at'))}")

    # -- actions --------------------------------------------------------
    def open_url(self) -> None:
        if not self.url:
            return
        if self.window.interactive:
            webbrowser.open(self.url)
        self.window.set_status(f"Open: {self.url}")

    def close(self) -> None:
        self.window.comment_windows.pop(self.key, None)
        self.destroy()
