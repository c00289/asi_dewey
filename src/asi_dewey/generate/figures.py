"""The one place Dewey calls ``asi_escher.build``, plus the bridge from catalog diagrams to documents.

``build_diagram`` serves the ``diagram`` verb: it runs Escher under ``warnings.catch_warnings``
so its ``LayoutWarning`` never escapes into a CLI or a test suite, and converts every
``LayoutIssue`` object into a plain dict so a ``Result`` serialises cleanly.

``add_figure`` serves the document builders: it builds a catalog diagram and hands it to
asi_gutenberg as a ``diagram`` block (``Document.diagram``), so Gutenberg renders the PNG into
``<out>/figures/`` itself when the triplet is built and numbers it as a figure.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

from ..schema import slugify

if TYPE_CHECKING:
    from ..brain import Brain

FORMATS = ("png", "svg", "dot", "mmd")
FIGURES_DIR = "figures"
DEFAULT_DPI = 160


def issues_to_dicts(issues: list[Any]) -> list[dict[str, Any]]:
    """Plain-data form of Escher ``LayoutIssue`` objects: ``kind``, ``message``, ``edge``, ``node``."""
    return [
        {
            "kind": getattr(i, "kind", "issue"),
            "message": getattr(i, "message", str(i)),
            "edge": list(i.edge) if getattr(i, "edge", None) else None,
            "node": getattr(i, "node", None),
        }
        for i in issues
    ]


def build_diagram(
    diagram: Any, out_dir: Any, name: str, *, formats: tuple[str, ...] = FORMATS, dpi: int = DEFAULT_DPI
) -> dict[str, Any]:
    """Lay out and write ``diagram`` as ``<out_dir>/<name>.<fmt>`` for every format.

    Returns ``{"paths": {fmt: path}, "size": [w, h], "nodes", "edges", "issues": [dict, ...]}``.
    """
    from asi_escher import LayoutWarning, build

    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"unknown format(s) {', '.join(unknown)}; choose from {', '.join(FORMATS)}")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", LayoutWarning)
        raw = build(diagram, str(out_dir), name, dpi=dpi, formats=tuple(formats))
    issues = issues_to_dicts(raw["issues"])
    for w in caught:
        if issubclass(w.category, LayoutWarning):
            if not issues:  # the issue list is the data; the warning only backs it up
                issues.append({"kind": "layout_warning", "message": str(w.message), "edge": None, "node": None})
        else:  # anything else (a matplotlib deprecation, say) is not ours to swallow
            warnings.warn(w.message, w.category, stacklevel=2)
    return {
        "paths": {fmt: str(raw[fmt]) for fmt in formats},
        "size": [int(raw["size"][0]), int(raw["size"][1])],
        "nodes": int(raw["nodes"]),
        "edges": int(raw["edges"]),
        "issues": issues,
    }


def figure_stem(key: str, params: dict[str, Any] | None = None) -> str:
    """File stem of a catalog diagram with these params: ``phase_flow_3``, ``task_flow``."""
    parts = [key, *(slugify(str(v)) for v in (params or {}).values() if str(v).strip())]
    return "_".join(p for p in parts if p)


def add_figure(doc: Any, brain: Brain, key: str, params: dict[str, Any] | None = None, caption: str = "") -> str:
    """Add catalog diagram ``key`` to a Gutenberg document as a numbered figure.

    The diagram is built now (so a bad key or param fails here) and attached as a ``diagram``
    block; asi_gutenberg renders it to ``figures/<stem>.png`` next to the Markdown when the
    document is built. Returns the relative path the Markdown will use (forward slashes).
    """
    from .factory import DiagramFactory

    params = dict(params or {})
    stem = figure_stem(key, params)
    diagram = DiagramFactory.create(key).build(brain, params)
    doc.diagram(diagram, caption, name=stem)
    return f"{FIGURES_DIR}/{stem}.png"
