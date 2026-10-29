"""Brain: the in-process API that wires every layer together.

A ``Brain`` owns one database. Front ends (the CLI, the window, and the window's local
automation server) hold a Brain and call ``execute``; Python callers can also reach the
services directly through ``service(entity)``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .automation.events import EventBus
from .commands import Dispatcher, Result
from .locks import guard, lock_dir
from .models import ModelFactory
from .repositories import RepositoryFactory
from .schema import LookupRegistry, SchemaRegistry, default_lookups, default_registry
from .services import ControlStructureService, EntityService, JiraService, TransferService, service_class
from .storage import StorageFactory
from .version import SCHEMA_VERSION, __version__

DEFAULT_DB_NAME = "dewey.db"
DEFAULT_WORKBOOK_NAME = "dewey.xlsx"
DEFAULT_OUT_NAME = "out"
ENV_DB = "ASI_DEWEY_DB"
ENV_WORKBOOK = "ASI_DEWEY_WORKBOOK"
ENV_OUT = "ASI_DEWEY_OUT"
ENV_CONFIG = "ASI_DEWEY_CONFIG"
CONFIG_NAME = "dewey.toml"
ENV_CONTROL_STRUCTURES = "ASI_DEWEY_CONTROL_STRUCTURES"
CONFIG_KEYS = ("db", "workbook", "out", "control_structures_dir")
TEXT_CONFIG_KEYS = ("jira_jql", "jira_live_jql")
# the private shelf of control-structure datasets the template builder reads (docs/control-structure-plan.md, 3)
DEFAULT_CONTROL_STRUCTURES_DIR = "../asi_standards/control-structures"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read ``dewey.toml``: the ``path`` given, else ``$ASI_DEWEY_CONFIG``, else ``./dewey.toml``.

    Keys ``db``, ``workbook``, ``out`` and ``control_structures_dir`` are paths; a relative one
    resolves against the config file's own directory, so the workbook and the generated files can
    live in another folder.
    ``jira_jql`` and ``jira_live_jql`` are plain text (the queries ``jira sync`` and ``jira live``
    run by default). Any other key is ignored (``jira_live_autofetch`` of 0.7.3 to 0.8.0 among
    them: the window it configured was removed in 0.8.1). Missing file: ``{}``.
    """
    import tomllib

    file = Path(path or os.environ.get(ENV_CONFIG) or Path.cwd() / CONFIG_NAME)
    if not file.is_file():
        return {}
    with file.open("rb") as handle:
        data = tomllib.load(handle)
    config: dict[str, Any] = {"path": str(file)}
    for key in CONFIG_KEYS:
        value = data.get(key)
        if value:
            value = Path(str(value)).expanduser()
            config[key] = str(value if value.is_absolute() else (file.parent / value).resolve())
    for key in TEXT_CONFIG_KEYS:
        if data.get(key):
            config[key] = str(data[key]).strip()
    return config


def resolve_db_path(db_path: str | Path | None, config: dict[str, Any] | None = None) -> str:
    """Explicit argument, else ``$ASI_DEWEY_DB``, else ``db`` in dewey.toml, else ./dewey.db."""
    if db_path is not None:
        return str(db_path)
    config = load_config() if config is None else config
    return os.environ.get(ENV_DB) or config.get("db") or str(Path.cwd() / DEFAULT_DB_NAME)


class Brain:
    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        registry: SchemaRegistry | None = None,
        lookups: LookupRegistry | None = None,
        backend: str = "sqlite",
        workbook_path: str | Path | None = None,
        out_dir: str | Path | None = None,
        wait: float = 0.0,
    ) -> None:
        """Open ``db_path``; ``wait`` seconds (polling every 250 ms) for the family slot first.

        Raises ``PrimaryToolBusy`` without touching the SQLite file when another primary tool
        (or another process of this one) is running; see ``asi_dewey.locks``.
        """
        from .schema import definitions  # noqa: F401  (registers the built-in entities)

        self.registry = registry or default_registry
        self.lookups = lookups or default_lookups
        self.config = load_config()
        self.db_path = resolve_db_path(db_path, self.config)
        self._closed = True  # until the slot is ours, close() has nothing to release
        guard.acquire(self.db_path, wait)
        self._closed = False
        try:
            self.storage = StorageFactory.create(backend, path=self.db_path)
            self.migration = self.storage.ensure_schema(self.registry)
            self.migration["uids_stamped"] = self.storage.stamp_uids(self.registry)
        except BaseException:
            self._closed = True
            guard.release(self.db_path)
            raise
        self.events = EventBus()
        self.models = ModelFactory(self.registry)
        self.repositories = RepositoryFactory(self.storage, self.registry)
        self._services: dict[str, EntityService] = {}
        self.transfer = TransferService(self)
        self.jira = JiraService(self)
        self.control_structures = ControlStructureService(self)
        self.dispatcher = Dispatcher(self)
        if workbook_path is not None:
            self.workbook_path = str(workbook_path)
        elif os.environ.get(ENV_WORKBOOK):
            self.workbook_path = os.environ[ENV_WORKBOOK]
        elif self.config.get("workbook"):
            self.workbook_path = self.config["workbook"]
        elif self.db_path == ":memory:":
            self.workbook_path = DEFAULT_WORKBOOK_NAME
        else:
            self.workbook_path = str(Path(self.db_path).with_name(DEFAULT_WORKBOOK_NAME))
        # generated diagrams and documents (views, like the workbook): argument, env, config, default
        if out_dir is not None:
            self.out_dir = str(out_dir)
        elif os.environ.get(ENV_OUT):
            self.out_dir = os.environ[ENV_OUT]
        elif self.config.get("out"):
            self.out_dir = self.config["out"]
        elif self.db_path == ":memory:":
            self.out_dir = DEFAULT_OUT_NAME
        else:
            self.out_dir = str(Path(self.db_path).with_name(DEFAULT_OUT_NAME))
        # the shelf the template builder reads: env, then dewey.toml, then beside the working directory
        if os.environ.get(ENV_CONTROL_STRUCTURES):
            self.control_structures_dir = os.environ[ENV_CONTROL_STRUCTURES]
        elif self.config.get("control_structures_dir"):
            self.control_structures_dir = self.config["control_structures_dir"]
        else:
            self.control_structures_dir = str((Path.cwd() / DEFAULT_CONTROL_STRUCTURES_DIR).resolve())

    # -- access ---------------------------------------------------------
    def service(self, entity: str) -> EntityService:
        schema = self.registry.get(entity)
        if schema.name not in self._services:
            self._services[schema.name] = service_class(schema.name)(
                schema, self.repositories.for_entity(schema), self.storage, self.lookups, self.events, self
            )
        return self._services[schema.name]

    @property
    def factory(self):
        """The ``ControlStructureFactory`` on this Brain (built on first use; see ``asi_dewey.stpa``)."""
        if not hasattr(self, "_factory"):
            from .stpa.factory import ControlStructureFactory

            self._factory = ControlStructureFactory(self)
        return self._factory

    def execute(
        self, verb: str, args: dict[str, Any] | None = None, *, actor: str = "python", **kwargs: Any
    ) -> Result:
        """Run a command.

        ``brain.execute("get", {"entity": "task", "id": 1})`` or ``brain.execute("get", entity="task", id=1)``.
        """
        merged = dict(args or {})
        merged.update(kwargs)
        return self.dispatcher.execute(verb, merged, actor)

    def execute_dict(self, payload: dict[str, Any], actor: str | None = None) -> Result:
        return self.dispatcher.execute_dict(payload, actor)

    def status(self) -> dict[str, Any]:
        return {
            "app_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "database": self.storage.describe(),
            "workbook_path": self.workbook_path,
            "out_dir": self.out_dir,
            "control_structures_dir": self.control_structures_dir,
            "config_path": self.config.get("path"),
            "lock_dir": str(lock_dir()),
            "locks": guard.describe(self.db_path),
            "entities": {s.name: self.service(s.name).count() for s in self.registry},
            "commands": self.dispatcher.factory.verbs(),
            "recent_audit": self.storage.audit_tail(5),
            "recent_events": self.events.last(5),
        }

    def close(self) -> None:
        """Close storage and give the slot back; safe to call more than once."""
        if self._closed:
            return
        try:
            self.storage.close()
        finally:
            self._closed = True
            guard.release(self.db_path)

    def __enter__(self) -> Brain:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Brain(db_path={self.db_path!r}, entities={len(self.registry)})"
