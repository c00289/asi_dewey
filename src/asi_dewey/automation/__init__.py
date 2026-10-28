"""Automation: CLI, event bus, script replay, and the local automation server.

``server.py`` is the loopback HTTP server a running window owns (``MainWindow.server``);
``session.py`` is the session file the CLI reads to forward a refused command to that window.
"""

from .events import EventBus

__all__ = ["EventBus"]
