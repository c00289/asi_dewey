"""EntityService: validated CRUD for one entity, with audit log and events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..automation.events import EventBus
from ..errors import CommandError, NotFound, StorageError, ValidationError
from ..repositories.sql_repo import SqlRepository
from ..schema import UID_FIELD, EntitySchema, LookupRegistry, new_uid, normalise_uid
from ..storage.base import Storage

LOAD_MODES = ("replace", "merge", "append")


class EntityService:
    def __init__(
        self,
        schema: EntitySchema,
        repository: SqlRepository,
        storage: Storage,
        lookups: LookupRegistry,
        events: EventBus,
        brain: Any = None,
    ) -> None:
        self.schema = schema
        self.repo = repository
        self.storage = storage
        self.lookups = lookups
        self.events = events
        self.brain = brain  # the Brain that owns the service, for rules that look at other entities

    # -- hooks (a subclass adds the rules of its entity; see services/control_structure_service.py) --
    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        """Entity rules on a create (``stored`` is ``None``) or an update (``stored`` is the row as it
        is, ``clean`` the fields about to change). Returns warnings; raises ``ValidationError`` to
        refuse. The default has no rules."""
        return []

    def before_delete(self, stored: dict[str, Any], cascade: bool, actor: str) -> None:
        """Called inside the transaction before the row goes; raises to refuse, or deletes dependants."""

    def after_change(self, action: str, row: dict[str, Any], actor: str) -> None:
        """Called after a create, update or delete was committed and the entity event published."""

    # -- reads ----------------------------------------------------------
    def list(
        self,
        filters: Mapping[str, Any] | None = None,
        order_by: str | Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.repo.list(filters, order_by, limit, offset)

    def count(self, filters: Mapping[str, Any] | None = None) -> int:
        return self.repo.count(filters)

    def get(self, row_id: int) -> dict[str, Any]:
        row = self.repo.get(row_id)
        if row is None:
            raise NotFound(f"{self.schema.name} {row_id} not found")
        return row

    def get_by_uid(self, uid: Any) -> dict[str, Any]:
        row = self.repo.get_by_uid(uid)
        if row is None:
            raise NotFound(f"{self.schema.name} uid {uid} not found")
        return row

    def resolve(self, ref: Any) -> int:
        """The id behind ``ref``: an int or an all-digit string is an id; a uid (any case, braces
        allowed) is looked up and an unknown one is ``NotFound``; anything else is a ``CommandError``."""
        if isinstance(ref, int) and not isinstance(ref, bool):
            return ref
        text = str(ref).strip()
        if text.isdigit():
            return int(text)
        if normalise_uid(text) is None:
            raise CommandError(f"{self.schema.name}: {ref!r} is neither an id nor a uid")
        return int(self.get_by_uid(text)["id"])

    # -- writes ---------------------------------------------------------
    def _insert(self, clean: dict[str, Any], row_id: int | None = None) -> dict[str, Any]:
        """``repo.create`` with the unique index on ``uid`` reported as a validation error, not a crash."""
        try:
            return self.repo.create(clean, row_id)
        except StorageError as exc:
            if "UNIQUE" in str(exc) and f".{UID_FIELD}" in str(exc):
                raise ValidationError(
                    self.schema.name, [f"{UID_FIELD} {clean.get(UID_FIELD)} is already used by another row"]
                ) from None
            raise

    def create(self, data: Mapping[str, Any], actor: str = "python") -> tuple[dict[str, Any], list[str]]:
        clean, warnings = self.schema.coerce_row(data, self.lookups)
        if not clean.get(UID_FIELD):
            clean[UID_FIELD] = new_uid()  # assigned once, here; a uid given by the caller (a file) is kept
        with self.storage.transaction():
            warnings.extend(self.check(clean, None))
            row = self._insert(clean)
            self.storage.audit(actor, "create", self.schema.name, row["id"], clean)
        self.events.publish("entity.created", entity=self.schema.name, id=row["id"], actor=actor, row=row)
        self.after_change("create", row, actor)
        return row, warnings

    def update(
        self, row_id: int, data: Mapping[str, Any], actor: str = "python"
    ) -> tuple[dict[str, Any], list[str]]:
        clean, warnings = self.schema.coerce_row(data, self.lookups, partial=True)
        stored = self.get(row_id)
        if UID_FIELD in clean:
            if clean[UID_FIELD] != stored.get(UID_FIELD):
                raise ValidationError(self.schema.name, [f"{UID_FIELD} is immutable"])
            del clean[UID_FIELD]  # the same value: a no-op
        with self.storage.transaction():
            warnings.extend(self.check(clean, stored))
            row = self.repo.update(row_id, clean)
            if row is None:
                raise NotFound(f"{self.schema.name} {row_id} not found")
            self.storage.audit(actor, "update", self.schema.name, row_id, clean)
        self.events.publish("entity.updated", entity=self.schema.name, id=row_id, actor=actor, row=row)
        self.after_change("update", row, actor)
        return row, warnings

    def delete(self, row_id: int, actor: str = "python", cascade: bool = False) -> None:
        """Delete one row. ``cascade`` lets an entity with dependants (a control structure, a
        controller, an edge) take them along; without it such a delete is refused."""
        with self.storage.transaction():
            stored = self.get(row_id)
            self.before_delete(stored, cascade, actor)
            if not self.repo.delete(row_id):
                raise NotFound(f"{self.schema.name} {row_id} not found")
            self.storage.audit(actor, "delete", self.schema.name, row_id)
        self.events.publish("entity.deleted", entity=self.schema.name, id=row_id, actor=actor)
        self.after_change("delete", stored, actor)

    def load_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        mode: str = "merge",
        actor: str = "import",
    ) -> dict[str, Any]:
        """Bulk load. ``replace`` wipes first; ``merge`` upserts; ``append`` inserts.

        Identity first (docs/hidden-identity-plan.md, 3.1): in every mode a row whose ``uid`` is
        already in the table updates that row, whatever its ``id`` in the file; otherwise, in merge
        mode, a row whose ``id`` exists updates that row by id and takes the file's uid when the file
        has one (the one deliberate identity reconciliation: a Kletz dump merged here hands the cached
        rows Kletz's uids; a warning names old and new; no other row holds that uid, or the match by
        uid above would have won, so the unique index never trips); otherwise the row is inserted
        keeping the file's uid when it has one (and its id in merge mode), with a fresh uid when it
        has none (a 0.7.x file). ``replace`` wipes first and keeps the file's uids. A workbook sheet
        carries no ``id`` column, so for a workbook the reconciliation is ``replace``.
        Rows are validated one by one; a bad row is reported and skipped, never fatal.
        """
        if mode not in LOAD_MODES:
            raise CommandError(f"mode must be one of {', '.join(LOAD_MODES)}, not {mode!r}")
        summary: dict[str, Any] = {
            "entity": self.schema.name, "mode": mode,
            "inserted": 0, "updated": 0, "deleted": 0, "skipped": 0,
            "warnings": [], "errors": [],
        }
        with self.storage.transaction():
            if mode == "replace":
                summary["deleted"] = self.repo.delete_all()
            for index, raw in enumerate(rows, start=1):
                try:
                    clean, warnings = self.schema.coerce_row(
                        {k: v for k, v in raw.items() if k != "id"}, self.lookups
                    )
                except Exception as exc:  # ValidationError or anything odd in a row
                    summary["errors"].append(f"row {index}: {exc}")
                    summary["skipped"] += 1
                    continue
                summary["warnings"].extend(f"row {index}: {w}" for w in warnings)
                row_id = raw.get("id")
                uid = clean.pop(UID_FIELD, None)
                known = self.repo.get_by_uid(uid) if uid else None
                if known is not None:
                    self.repo.update(int(known["id"]), clean)
                    summary["updated"] += 1
                elif mode == "merge" and row_id is not None and self.repo.exists(int(row_id)):
                    stored = self.repo.get(int(row_id))
                    if uid and stored is not None and uid != stored.get(UID_FIELD):
                        clean[UID_FIELD] = uid  # plan 3.1: the file's identity wins on a merge by id
                        summary["warnings"].append(
                            f"row {index}: {self.schema.name} {row_id} takes the file's uid {uid}"
                            f" (was {stored.get(UID_FIELD)})"
                        )
                    self.repo.update(int(row_id), clean)
                    summary["updated"] += 1
                else:
                    keep = int(row_id) if (mode == "merge" and row_id is not None) else None
                    self._insert({**clean, UID_FIELD: uid or new_uid()}, keep)
                    summary["inserted"] += 1
            self.storage.audit(
                actor, f"load:{mode}", self.schema.name, None,
                {k: summary[k] for k in ("inserted", "updated", "deleted", "skipped")},
            )
        self.events.publish("entity.loaded", entity=self.schema.name, actor=actor, summary=summary)
        return summary
