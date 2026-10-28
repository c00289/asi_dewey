"""Exception hierarchy. Every error the core raises on purpose derives from BrainError."""

from __future__ import annotations


class BrainError(Exception):
    """Base class for errors raised by ASI Dewey."""


class ValidationError(BrainError, ValueError):
    """A row did not satisfy its entity schema. ``errors`` lists every problem found."""

    def __init__(self, entity: str, errors: list[str] | tuple[str, ...]):
        self.entity = entity
        self.errors = list(errors)
        super().__init__(f"{entity}: " + "; ".join(self.errors))


class NotFound(BrainError, LookupError):
    """A row, entity, command, or file was asked for and does not exist."""


class CommandError(BrainError):
    """A command was called with bad arguments."""


class StorageError(BrainError):
    """The storage backend could not complete an operation."""


class PrimaryToolBusy(BrainError):
    """Another primary tool (or another process of this one) holds the slot; see ``asi_dewey.locks``.

    ``slot`` is ``"family"`` (a primary tool is running) or ``"database"`` (this database is open);
    ``holder`` is the parsed ``.json`` written beside the lock, or ``None`` when it is unreadable.
    """

    def __init__(self, slot: str, holder: dict | None = None, message: str | None = None):
        self.slot = slot
        self.holder = holder
        if message is None:
            from .locks import describe_holder

            message = describe_holder(slot, holder)
        super().__init__(message)
