"""The ``diagram`` and ``document`` verbs: views generated with asi_escher and asi_gutenberg.

Without a name both verbs list their catalog, so an agent discovers diagrams and documents the
way it discovers entities with ``schema``. With a name they build into ``--out`` or
``Brain.out_dir``, record an audit entry (action ``generate``) and publish a ``generated``
event. Layout issues become ``Result.warnings``; a bad name or param is a ``Result.failure``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from ..errors import CommandError
from ..generate import DiagramFactory, DocumentFactory
from ..generate.figures import DEFAULT_DPI, FIGURES_DIR, FORMATS, build_diagram
from .base import Argument, Command, Context, Result, parse_kv
from .factory import register_command

OUT = Argument("out", "Output folder (default: `out` from dewey.toml, $ASI_DEWEY_OUT, or out/ next to the database)",
               flag=True, type="path")
PARAM = Argument("param", "Builder parameter as key=value (repeatable; see the catalog)", flag=True, type="kv",
                 multiple=True)
DOC_FORMATS = ("md", "pdf", "docx")


def _record(ctx: Context, kind: str, name: str, paths: dict[str, str]) -> None:
    ctx.brain.storage.audit(ctx.actor, "generate", name, None, {"kind": kind, "paths": paths})
    ctx.brain.events.publish("generated", kind=kind, name=name, paths=paths, actor=ctx.actor)


def _formats(text: Any) -> tuple[str, ...]:
    if not text:
        return FORMATS
    if isinstance(text, (list, tuple)):
        text = ",".join(str(t) for t in text)
    formats = tuple(dict.fromkeys(f.strip().lower() for f in str(text).split(",") if f.strip()))
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise CommandError(f"unknown format(s) {', '.join(unknown)}; choose from {', '.join(FORMATS)}")
    return formats or FORMATS


def _out_dir(ctx: Context, args: dict[str, Any]) -> Path:
    return Path(args.get("out") or ctx.brain.out_dir)


@register_command
class DiagramCommand(Command):
    verb = "diagram"
    help = "Render a catalog diagram with asi_escher (no name: list the catalog)."
    arguments = (
        Argument("name", "Diagram key (omit for the catalog)"),
        OUT,
        Argument("formats", "Comma-separated subset of png,svg,dot,mmd", flag=True, default=",".join(FORMATS)),
        PARAM,
        Argument("dpi", "PNG resolution", flag=True, type="int", default=DEFAULT_DPI),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        if not args.get("name"):
            return Result.success({"catalog": DiagramFactory.catalog()})
        generator = DiagramFactory.create(args["name"])
        key = generator.spec.key
        diagram = generator.build(ctx.brain, parse_kv(args.get("param")))
        built = build_diagram(
            diagram, _out_dir(ctx, args), key, formats=_formats(args.get("formats")),
            dpi=int(args.get("dpi") or DEFAULT_DPI),
        )
        paths = built["paths"]
        data = {
            "name": key, "title": diagram.title, "paths": paths,
            "primary": paths.get("png") or next(iter(paths.values())),
            "size": built["size"], "nodes": built["nodes"], "edges": built["edges"], "issues": built["issues"],
        }
        _record(ctx, "diagram", key, paths)
        return Result.success(data, [i["message"] for i in built["issues"]])


def _build_with_fallback(doc: Any, out_dir: Path, stem: str) -> tuple[dict[str, Any], str | None]:
    """Build the triplet; if the PDF is locked (open in a viewer) retry with a timestamped stem."""
    from asi_gutenberg import build

    try:
        return build(doc, str(out_dir), stem, figures_dir=FIGURES_DIR), None
    except PermissionError:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        alt = f"{stem}_{stamp}"
        return build(doc, str(out_dir), alt, figures_dir=FIGURES_DIR), (
            f"{stem}.pdf is locked (open in another program); wrote {alt}.pdf instead"
        )


def _plain(value: Any) -> Any:
    """Tuples from the generators become lists so ``Result.to_json`` and the audit log stay plain."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


@register_command
class DocumentCommand(Command):
    verb = "document"
    help = "Build a catalog document with asi_gutenberg: .md, .pdf and .docx with figures (no name: list the catalog)."
    arguments = (Argument("name", "Document key (omit for the catalog)"), OUT, PARAM)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        if not args.get("name"):
            return Result.success({"catalog": DocumentFactory.catalog()})
        generator = DocumentFactory.create(args["name"])
        key = generator.spec.key
        out_dir = _out_dir(ctx, args)
        doc = generator.build(ctx.brain, parse_kv(args.get("param")))
        doc.meta.author = ctx.actor  # the actor that ran the command, never a person's name
        doc.revision(doc.meta.revision, doc.meta.date, ctx.actor, "Generated from the database")

        # asi_gutenberg renders the diagram blocks into <out>/figures/ before writing the triplet
        built, locked = _build_with_fallback(doc, out_dir, key)
        issues = [str(i) for i in built.get("issues", [])]  # trace problems and "diagram <stem>: ..." layouts
        warnings = [*issues, *([locked] if locked else [])]
        paths = {fmt: str(built[fmt]) for fmt in DOC_FORMATS}
        diagrams = _plain(built.get("diagrams", []))
        stats = {k: v for k, v in built.items() if k not in (*DOC_FORMATS, "pages", "issues", "diagrams")}
        data = {
            "name": key, "title": doc.title, "paths": paths, "primary": paths["pdf"],
            "pages": built.get("pages"), "diagrams": diagrams, "stats": stats, "issues": issues,
        }
        _record(ctx, "document", key, paths)
        return Result.success(data, warnings)
