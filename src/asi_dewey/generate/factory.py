"""DiagramFactory and DocumentFactory: catalog key -> builder, filled by registration.

They mirror ``ExporterFactory``: a class-level registry, ``create(key)``, ``keys()``,
``specs()``, and a ``NotFound`` that lists the known keys on a miss. A builder is a plain
function ``(brain, params) -> asi_escher.Diagram`` or ``-> asi_gutenberg.Document``; it reads
the database only through ``brain.service(entity)`` and ``brain.registry``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from ..errors import NotFound
from .base import Spec

if TYPE_CHECKING:
    from ..brain import Brain

Builder = Callable[["Brain", dict[str, str]], Any]


@dataclass(frozen=True)
class Generator:
    """A registered builder with its spec. ``build`` validates the params first."""

    spec: Spec
    builder: Builder

    def build(self, brain: Brain, params: dict[str, Any] | None = None) -> Any:
        return self.builder(brain, self.spec.check_params(params))


class GeneratorFactory:
    kind: ClassVar[str] = "generator"
    _registry: ClassVar[dict[str, Generator]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._registry = {}  # every factory owns its catalog

    @classmethod
    def register(cls, spec: Spec) -> Callable[[Builder], Builder]:
        def decorator(builder: Builder) -> Builder:
            if spec.key in cls._registry:
                raise ValueError(f"{cls.kind} {spec.key!r} already registered")
            cls._registry[spec.key] = Generator(spec, builder)
            return builder

        return decorator

    @classmethod
    def create(cls, key: str) -> Generator:
        try:
            return cls._registry[str(key)]
        except KeyError:
            raise NotFound(f"unknown {cls.kind} {key!r}; known: {', '.join(cls._registry)}") from None

    @classmethod
    def keys(cls) -> list[str]:
        return list(cls._registry)

    @classmethod
    def specs(cls) -> list[Spec]:
        return [g.spec for g in cls._registry.values()]

    @classmethod
    def catalog(cls) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in cls.specs()]

    @classmethod
    def __contains__(cls, key: object) -> bool:  # pragma: no cover - convenience
        return key in cls._registry


class DiagramFactory(GeneratorFactory):
    kind = "diagram"


class DocumentFactory(GeneratorFactory):
    kind = "document"


def register_diagram(spec: Spec) -> Callable[[Builder], Builder]:
    return DiagramFactory.register(spec)


def register_document(spec: Spec) -> Callable[[Builder], Builder]:
    return DocumentFactory.register(spec)
