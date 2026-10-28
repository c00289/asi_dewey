"""Entry point for the desktop window: ``asi-dewey-gui`` or ``python -m asi_dewey gui``."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from ..version import __version__
from .theme import ThemeFactory

if TYPE_CHECKING:
    from ..brain import Brain
    from ..errors import PrimaryToolBusy

EXIT_BUSY = 3  # another primary tool holds the slot (same code as the CLI)


def launch(brain: Brain, interactive: bool = True, theme: str | None = None, server: bool = True) -> None:
    """Open the main window on an existing Brain and block until it is closed.

    ``theme`` is a one-off override; ``ThemeFactory.resolve`` falls back to ``$ASI_DEWEY_THEME``,
    then the latched preference, then the house default. An override is never latched.
    ``server=False`` opens the window without its local automation server (``--no-server``);
    ``ASI_DEWEY_AUTOMATION=off`` does the same for every launch.
    """
    from .main_window import MainWindow

    window = MainWindow(brain, interactive=interactive, theme=ThemeFactory.resolve(theme), server=server)
    window.mainloop()


def ask_retry(exc: PrimaryToolBusy) -> bool:
    """The busy dialog: the holder line and two buttons, Retry (True) and Quit (False)."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("ASI Dewey is waiting")
    root.resizable(False, False)
    answer = {"retry": False}

    def choose(retry: bool) -> None:
        answer["retry"] = retry
        root.destroy()

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Another primary tool is running.", font=("TkHeadingFont", 11, "bold")).pack(anchor="w")
    ttk.Label(frame, text=str(exc), wraplength=520, justify="left").pack(anchor="w", pady=(8, 16))
    buttons = ttk.Frame(frame)
    buttons.pack(anchor="e")
    retry = ttk.Button(buttons, text="Retry", command=lambda: choose(True), default="active")
    retry.pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Quit", command=lambda: choose(False)).pack(side="left")
    root.bind("<Return>", lambda _e: choose(True))
    root.bind("<Escape>", lambda _e: choose(False))
    root.protocol("WM_DELETE_WINDOW", lambda: choose(False))
    retry.focus_set()
    root.eval("tk::PlaceWindow . center")
    root.mainloop()
    return answer["retry"]


def main(argv: list[str] | None = None, interactive: bool = True) -> int:
    """0 when the window closed; 3 when another primary tool is running and the user quit (or
    ``interactive`` is False, which skips the dialog)."""
    from ..brain import Brain
    from ..errors import PrimaryToolBusy

    parser = argparse.ArgumentParser(prog="asi-dewey-gui", description="ASI Dewey desktop window.")
    parser.add_argument("--db", help="SQLite file (default: $ASI_DEWEY_DB or ./dewey.db)")
    parser.add_argument(
        "--wait",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Wait up to SECONDS (polling every 250 ms) for the family slot when another primary tool "
        "is running, before showing the Retry / Quit dialog (exit code 3 on Quit)",
    )
    parser.add_argument(
        "--theme",
        help="Theme key for this launch only, e.g. pink-noir or plain (see `asi-dewey theme`); "
        "also $ASI_DEWEY_THEME. Default: the latched preference, else cyan-neon",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Open the window without its local automation server for this launch (also ASI_DEWEY_AUTOMATION=off); "
        "`asi-dewey ...` is then refused with exit code 3 while the window is open",
    )
    parser.add_argument("--version", action="version", version=f"asi-dewey-gui {__version__}")
    ns = parser.parse_args(argv)
    while True:
        try:
            brain = Brain(ns.db, wait=ns.wait)
        except PrimaryToolBusy as exc:
            if interactive and ask_retry(exc):
                continue  # Retry re-attempts once per click; the dialog comes back while it is busy
            return EXIT_BUSY
        with brain:
            launch(brain, interactive=interactive, theme=ns.theme, server=not ns.no_server)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
