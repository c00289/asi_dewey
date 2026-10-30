"""Command layer: the single entry point every front end uses."""

from . import crud, generate, gui, handover, jira, session, theme, transfer  # noqa: E402, F401  (registers the verbs)
from .base import Argument, Command, Context, Result
from .dispatcher import Dispatcher
from .factory import CommandFactory, default_command_factory, register_command

__all__ = [
    "Argument",
    "Command",
    "CommandFactory",
    "Context",
    "Dispatcher",
    "Result",
    "default_command_factory",
    "register_command",
]
