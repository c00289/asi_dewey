"""MainWindow: navigation on the left, one Screen at a time on the right, status bar below.

The window never touches storage directly. Every change goes through ``run`` which calls
``Brain.execute`` with actor ``gui``; the event bus then refreshes whatever screen is open,
so edits made by the CLI or an agent against the same Brain appear live too. Two events do not
refresh a screen: ``theme.changed`` repaints the window, and ``jira.live`` (a forwarded
``jira live``) changes no database row. Every verb runs on the Tk thread: the JIRA Live Data
screen, which fetched on a worker thread, was removed in 0.8.1.

The window owns the local automation server (``automation/server.py``): it starts it after the
first screen is shown, writes the session file, shows the port in the online indicator, and stops
it in ``close()`` before the root is destroyed. A failure to bind or to write the file is a
status-bar warning, never a failed launch. ``remote_guard`` is the one place a remote command is
refused on the window's behalf (a dirty screen; never a dialog).
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..automation.server import AutomationServer
from ..automation.session import automation_enabled, clear_session, session_path, write_session
from ..commands import Result
from ..locks import lock_dir
from ..version import __version__
from .palettes import FAMILIES
from .screens import Screen, ScreenFactory, build_default_screens
from .theme import Theme, ThemeFactory

if TYPE_CHECKING:
    from ..brain import Brain

PLAIN_THEME = "plain"


DEFAULT_SIZE = (1280, 800)


def fit_geometry(width: int, height: int, screen_w: int, screen_h: int) -> tuple[str, bool]:
    """Geometry for a window that wants ``width`` x ``height`` on a ``screen_w`` x ``screen_h`` screen.

    Returns the geometry string and whether the window should open maximised ("zoomed"). The frame,
    the title bar and the taskbar take about 100 px, so on a laptop screen that cannot hold the full
    size a window of that size puts the status bar and the theme picker under the taskbar, where
    nobody can see them; maximising fits the work area exactly.
    """
    margin_w, margin_h = 16, 100
    if width + margin_w <= screen_w and height + margin_h <= screen_h:
        return f"{width}x{height}", False
    w = max(1, min(width, screen_w - margin_w))
    h = max(1, min(height, screen_h - margin_h))
    return f"{w}x{h}+0+0", True


def theme_badge(title: str) -> str:
    """The status-bar badge for a theme title: upper-cased, any parenthetical dropped (``PLAIN``)."""
    return re.sub(r"\s*\([^)]*\)", "", title).strip().upper()


ONLINE = "◉ ONLINE"


class MainWindow(tk.Tk):
    def __init__(
        self,
        brain: Brain,
        factory: ScreenFactory | None = None,
        interactive: bool = True,
        theme: str | Theme | None = None,
        server: bool = True,
    ) -> None:
        super().__init__()
        self.brain = brain
        self.interactive = interactive
        self.server: AutomationServer | None = None  # set once it has bound; read by the status bar
        self._closed = False
        warning: str | None = None
        if isinstance(theme, Theme):
            self.theme = theme
        else:
            # --theme / $ASI_DEWEY_THEME / latched preference / house default; a bad latch only warns
            _, warning = ThemeFactory.latched()
            self.theme = ThemeFactory.create(ThemeFactory.resolve(theme))
        self.theme.apply(self)
        # Tk's class binding makes a ttk combobox (and spinbox) pick its next value on the mouse wheel, and
        # ScrollableFrame scrolls the form on the same wheel, so scrolling with the pointer passing over a
        # task class or a lifecycle phase silently changed it (asi_kletz 0.15.2 found it in the owner's Safety
        # Plan). The window drops both class bindings once: the wheel scrolls, a value changes by a pick only.
        for widget_class in ("TCombobox", "TSpinbox"):
            self.unbind_class(widget_class, "<MouseWheel>")
        self.factory = factory or build_default_screens(brain)
        self._screens: dict[str, Screen] = {}
        self.current: Screen | None = None
        self.current_key: str | None = None
        self._refresh_job: str | None = None
        self.theme_var = tk.StringVar(value=self.theme.title)  # shared by the picker and View > Theme
        self._theme_keys = self._titles_to_keys()

        self.title(f"ASI Dewey {__version__}")
        geometry, zoom = fit_geometry(*DEFAULT_SIZE, self.winfo_screenwidth(), self.winfo_screenheight())
        self.geometry(geometry)
        if zoom:
            try:
                self.state("zoomed")  # Windows: fill the work area, taskbar excluded
            except tk.TclError:
                pass  # elsewhere the clamped geometry already fits
        self.minsize(900, 600)
        self._build_menu()
        self._build_body()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._handler = self.brain.events.subscribe("*", self._on_event)
        self.show("dashboard" if "dashboard" in self.factory else self.factory.items()[0][0])
        if server and automation_enabled():
            warning = self._start_server() or warning
        if warning:
            self.set_status(f"Warning: {warning}")

    # -- the automation server ------------------------------------------
    def _start_server(self) -> str | None:
        """Bind, serve, write the session file and show the port; a failure is the warning returned."""
        server = AutomationServer(self)
        try:
            server.start()
        except OSError as exc:
            return f"automation server not started ({exc}); the window runs as with --no-server"
        try:
            write_session(server.port, server.token, self.brain.db_path, server.started_at, host=server.host)
        except OSError as exc:
            server.stop()
            return f"session file not written ({session_path()}: {exc}); the window runs as with --no-server"
        self.server = server
        self.online_var.set(self._online_text())
        return None

    def _stop_server(self) -> None:
        server, self.server = self.server, None
        if server is not None:
            server.stop()
            clear_session()

    def _online_text(self) -> str:
        return f"{ONLINE} :{self.server.port}" if self.server is not None else ONLINE

    def remote_guard(self, verb: str, args: dict[str, Any]) -> Result | None:
        """The one hook a remote command passes before ``brain.execute``: a ``Result`` refuses it.

        Today one rule: a remote ``theme`` pick never prompts, so when the open screen has unsaved
        edits (``is_dirty()``) it is refused and the preference is not latched either. This is a
        safety hook for "this would destroy what the engineer is typing", not a permission system.
        """
        if verb == "theme" and args.get("key"):
            dirty = getattr(self.current, "is_dirty", None)
            if callable(dirty) and dirty():
                result = Result.failure(
                    f"theme change refused: the {self.current_key} screen has unsaved edits", verb="theme"
                )
                result.warnings = ["save or discard the edits, then retry"]
                return result
        return None

    # -- layout ---------------------------------------------------------
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Export workbook", accelerator="Ctrl+E", command=self.export_workbook)
        file_menu.add_command(label="Import workbook…", command=lambda: self.show("transfer"))
        file_menu.add_command(label="Build document…", command=self.build_document)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", accelerator="Ctrl+Q", command=self.close)
        menu.add_cascade(label="File", menu=file_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        for key, title in self.factory.items():
            view_menu.add_command(label=title, command=lambda k=key: self.show(k))
        view_menu.add_separator()
        view_menu.add_cascade(label="Theme", menu=self._build_theme_menu(view_menu))
        menu.add_cascade(label="View", menu=view_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self.about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menu)

    def _build_theme_menu(self, parent: tk.Menu) -> tk.Menu:
        """View > Theme: one submenu per family with a radio item per tone, then Plain (native)."""
        theme_menu = tk.Menu(parent, tearoff=False)
        entries = ThemeFactory.entries()
        for family in FAMILIES:
            family_menu = tk.Menu(theme_menu, tearoff=False)
            for entry in entries:
                if entry.family == family:
                    family_menu.add_radiobutton(
                        label=entry.tone.capitalize(), variable=self.theme_var, value=entry.title,
                        command=lambda k=entry.key: self.pick_theme(k),
                    )
            theme_menu.add_cascade(label=family.capitalize(), menu=family_menu)
        theme_menu.add_separator()
        plain = ThemeFactory.get(PLAIN_THEME)
        theme_menu.add_radiobutton(
            label=plain.title, variable=self.theme_var, value=plain.title,
            command=lambda: self.pick_theme(PLAIN_THEME),
        )
        return theme_menu

    def _build_body(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        nav_box = ttk.Frame(paned, padding=(0, 0), style="Nav.TFrame")
        brand = ttk.Frame(nav_box, padding=(12, 14, 12, 10), style="Nav.TFrame")
        brand.pack(fill="x")
        ttk.Label(brand, text="ASI DEWEY", style="Title.TLabel").pack(anchor="w")
        ttk.Label(brand, text=f"FUSA // v{__version__}", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Frame(nav_box, height=1, style="Rule.TFrame").pack(fill="x", padx=8)

        # the theme picker sits at the foot of the navigation column; packed first so it keeps its room
        picker = ttk.Frame(nav_box, padding=(8, 4, 8, 10), style="Nav.TFrame")
        picker.pack(fill="x", side="bottom")
        ttk.Label(picker, text="THEME", style="Caption.TLabel").pack(anchor="w")
        self.theme_box = ttk.Combobox(
            picker, textvariable=self.theme_var, values=list(self._theme_keys), state="readonly",
        )
        self.theme_box.pack(fill="x", pady=(2, 0))
        self.theme_box.bind("<<ComboboxSelected>>", self._on_theme_pick)

        self.nav = tk.Listbox(nav_box, exportselection=False, activestyle="none", width=24, font=self.theme.ui)
        for _, title in self.factory.items():
            self.nav.insert("end", f"   {title.upper()}")
        self.nav.pack(fill="both", expand=True, padx=8, pady=8)
        self.nav.bind("<<ListboxSelect>>", self._on_nav)
        paned.add(nav_box, weight=0)
        self.content = ttk.Frame(paned)
        paned.add(self.content, weight=1)

        ttk.Frame(self, height=1, style="Rule.TFrame").pack(fill="x", side="bottom")
        status = ttk.Frame(self, padding=(10, 4), style="Status.TFrame")
        status.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready")
        # the online indicator (with the automation port while the server is up) and the theme
        # badge are rebuilt from self.server and self.theme by set_theme; the server survives it
        self.online_var = tk.StringVar(value=self._online_text())
        self.badge_var = tk.StringVar(value=theme_badge(self.theme.title))
        self.online_label = ttk.Label(status, textvariable=self.online_var, style="Status.TLabel")
        self.online_label.pack(side="left", padx=(0, 14))
        self.badge_label = ttk.Label(
            status, textvariable=self.badge_var, style="StatusMuted.TLabel", font=self.theme.mono
        )
        self.badge_label.pack(side="left", padx=(0, 14))
        ttk.Label(status, textvariable=self.status_var, anchor="w", style="Status.TLabel").pack(
            side="left", fill="x", expand=True
        )
        ttk.Label(status, text=self.brain.db_path, style="StatusMuted.TLabel").pack(side="right")
        paned.pack(fill="both", expand=True)  # packed last: a short window squeezes the body, never the status bar

    def _bind_keys(self) -> None:
        self.bind_all("<Control-n>", lambda e: self._delegate("new"))
        self.bind_all("<Control-s>", lambda e: self._delegate("save"))
        self.bind_all("<Control-e>", lambda e: self.export_workbook())
        self.bind_all("<Control-q>", lambda e: self.close())
        self.bind_all("<F5>", lambda e: self.current and self.current.refresh())

    def _delegate(self, method: str) -> None:
        handler = getattr(self.current, method, None)
        if callable(handler):
            handler()

    # -- navigation -----------------------------------------------------
    def show(self, key: str) -> Screen:
        if key not in self._screens:
            self._screens[key] = self.factory.create(key, self.content, self)
        if self.current is not None and self.current is not self._screens[key]:
            self.current.pack_forget()
        self.current = self._screens[key]
        self.current_key = key
        self.current.pack(fill="both", expand=True)
        keys = [k for k, _ in self.factory.items()]
        index = keys.index(key)
        self.nav.selection_clear(0, "end")
        self.nav.selection_set(index)
        self.nav.see(index)
        self.title(f"ASI Dewey {__version__} — {self.factory.title(key)}")
        self.current.on_show()
        return self.current

    def _on_nav(self, _event: tk.Event) -> None:
        selection = self.nav.curselection()
        if selection:
            key = self.factory.items()[selection[0]][0]
            if key != self.current_key:
                self.show(key)

    # -- theme ----------------------------------------------------------
    @staticmethod
    def _titles_to_keys() -> dict[str, str]:
        """Picker rows in order: the 32 catalog titles, then Plain (native)."""
        titles = {entry.title: entry.key for entry in ThemeFactory.entries()}
        titles[ThemeFactory.get(PLAIN_THEME).title] = PLAIN_THEME
        return titles

    def _sync_picker(self) -> None:
        """The picker always shows the theme that is painting the window."""
        self.theme_var.set(self.theme.title)

    def _on_theme_pick(self, _event: tk.Event) -> None:
        key = self._theme_keys.get(self.theme_var.get())
        if key is None:
            self._sync_picker()
            return
        self.theme_box.selection_clear()
        self.pick_theme(key)

    def pick_theme(self, key: str) -> Result:
        """Latch ``key`` through the ``theme`` verb; the ``theme.changed`` event then repaints the window."""
        dirty = getattr(self.current, "is_dirty", None)
        if callable(dirty) and dirty():
            question = "Changing the theme rebuilds this screen and drops unsaved edits. Go on?"
            if not self.confirm("Change theme", question):
                self._sync_picker()
                return Result.failure("theme change cancelled", verb="theme")
        result = self.run("theme", key=key)
        if not result.ok:
            self._sync_picker()
        return result

    def set_theme(self, key: str) -> None:
        """Repaint by rebuilding: every tk widget reads the option database only when it is created."""
        self._cancel_refresh()
        current = self.current_key
        self.theme = ThemeFactory.create(key)
        self.theme.apply(self)  # fonts, ttk base, styles, option database
        self.theme_var.set(self.theme.title)
        for child in self.winfo_children():  # menu, paned body, rule, status bar
            child.destroy()
        self._screens.clear()
        self.current = None
        self.current_key = None
        self._build_menu()
        self._build_body()  # includes the picker, now showing `key`
        self.show(current or "dashboard")
        self.set_status(f"Theme: {self.theme.title}")

    # -- feedback -------------------------------------------------------
    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def status_text(self) -> str:
        return self.status_var.get()

    def notify_error(self, title: str, message: str) -> None:
        self.set_status(f"Error: {message}")
        if self.interactive:
            messagebox.showerror(title, message, parent=self)

    def confirm(self, title: str, message: str) -> bool:
        if not self.interactive:
            return True
        return bool(messagebox.askyesno(title, message, parent=self))

    def about(self) -> None:
        text = (
            f"ASI Dewey {__version__}\nFuSa working-knowledge API with a tkinter front end."
            f"\n\nDatabase: {self.brain.db_path}"
            f"\nLock directory: {lock_dir()}  (one primary tool at a time; see ASI_PRIMARY_LOCK_DIR)"
            f"\nAutomation: {self.server.address if self.server is not None else 'off'}"
            f"  (session file: {session_path()}; see `asi-dewey session`)"
        )
        if self.interactive:
            messagebox.showinfo("About ASI Dewey", text, parent=self)
        self.set_status(text.replace("\n", "  "))

    # -- commands -------------------------------------------------------
    def run(self, verb: str, **args: Any) -> Result:
        """Execute as actor ``gui``; a failure is a status-bar line plus a dialog when interactive."""
        result = self.brain.execute(verb, args, actor="gui")
        if not result.ok:
            self.notify_error(f"{verb} failed", "; ".join(result.errors) or "unknown error")
        elif result.warnings:
            self.set_status("Warning: " + "; ".join(result.warnings))
        return result

    def build_document(self) -> Screen:
        """File > Build document…: the Generate screen with the Documents list focused."""
        screen = self.show("generate")
        focus = getattr(screen, "focus_documents", None)
        if callable(focus):
            focus()
        return screen

    def export_workbook(self) -> Result:
        result = self.run("export", format="excel")
        if result.ok:
            note = f"Workbook written: {result.data['path']}"
            if result.warnings:
                note += " (" + "; ".join(result.warnings) + ")"
            self.set_status(note)
        return result

    # -- events ---------------------------------------------------------
    def _on_event(self, topic: str, event: dict[str, Any]) -> None:
        if topic == "theme.changed":
            key = event.get("theme")
            if isinstance(key, str) and key in ThemeFactory.keys():
                if ThemeFactory.get(key) is type(self.theme):  # same look already painted: nothing to rebuild
                    self.set_status(f"Theme: {self.theme.title}")
                else:
                    self.set_theme(key)
            return
        if topic == "jira.live":
            return  # a forwarded `jira live`: no database row changed, nothing to refresh
        if self._refresh_job is not None:
            return
        self._refresh_job = self.after(50, self._refresh_after_event)

    def _refresh_after_event(self) -> None:
        self._refresh_job = None
        if self.current is not None:
            self.current.refresh()

    def _cancel_refresh(self) -> None:
        """Never let a pending refresh fire into widgets that are about to be destroyed."""
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None

    def close(self) -> None:
        """Stop the server and clear the session file first, then destroy; safe to call twice."""
        if self._closed:
            return
        self._closed = True
        self._stop_server()  # a request in flight gets its answer, and the CLI stops forwarding now
        self.brain.events.unsubscribe("*", self._handler)
        self._cancel_refresh()
        self.destroy()
