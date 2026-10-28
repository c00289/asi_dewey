"""Spec and Param: what a catalog entry (a diagram or a document) declares about itself.

A ``Spec`` is the agent-facing description of one generator: its key, a title, a sentence of
description, and the parameters its builder accepts. ``check_params`` turns a bad call into a
``CommandError`` listing the problem, so the dispatcher answers with a ``Result.failure``
instead of a traceback.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..errors import CommandError


@dataclass(frozen=True)
class Param:
    """One parameter of a builder. ``lookup`` names a lookup list the value comes from."""

    name: str
    help: str = ""
    required: bool = False
    default: str | None = None
    lookup: str | None = None

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ValueError(f"param name {self.name!r} must be a Python identifier")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "help": self.help, "required": self.required,
            "default": self.default, "lookup": self.lookup,
        }


@dataclass(frozen=True)
class Spec:
    """Describes one catalog entry."""

    key: str
    title: str
    description: str = ""
    params: tuple[Param, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.isidentifier():
            raise ValueError(f"catalog key {self.key!r} must be a Python identifier")
        names = [p.name for p in self.params]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.key}: duplicate param names")
        object.__setattr__(self, "params", tuple(self.params))

    @property
    def param_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)

    def param(self, name: str) -> Param:
        for p in self.params:
            if p.name == name:
                return p
        raise KeyError(f"{self.key} has no param {name!r}")

    def check_params(self, params: Mapping[str, Any] | None) -> dict[str, str]:
        """Validate caller parameters; return them with defaults filled in.

        Unknown names and missing required values raise ``CommandError`` naming them and
        listing what the builder accepts.
        """
        given = {str(k): ("" if v is None else str(v)).strip() for k, v in (params or {}).items()}
        known = self.param_names
        errors: list[str] = []
        unknown = sorted(set(given) - set(known))
        if unknown:
            errors.append(
                f"{self.key}: unknown param(s) {', '.join(unknown)}; accepts {', '.join(known) or 'no params'}"
            )
        for p in self.params:
            if p.required and not given.get(p.name):
                errors.append(f"{self.key}: missing required param {p.name!r} ({p.help})" if p.help
                              else f"{self.key}: missing required param {p.name!r}")
        if errors:
            raise CommandError("; ".join(errors))
        clean = {p.name: p.default for p in self.params if p.default is not None}
        clean.update({k: v for k, v in given.items() if v})
        return clean

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "title": self.title, "description": self.description,
            "params": [p.to_dict() for p in self.params],
        }
