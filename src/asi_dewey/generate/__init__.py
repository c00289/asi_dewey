"""Generate: diagrams with asi_escher and documents with asi_gutenberg, from the database.

Diagrams and documents are *views*, exactly like the workbook: regenerated on demand, never
read back. Each lives in a catalog behind a factory, and a new one is one builder function
plus one ``@register_diagram(Spec(...))`` or ``@register_document(Spec(...))``.

The generators are imported lazily inside the builders and ``figures.py``, so importing this
package (which the command layer does at start-up) pulls in neither matplotlib nor reportlab.
"""

from . import diagrams, documents  # noqa: E402, F401  (registers the built-in catalogs)
from .base import Param, Spec
from .factory import DiagramFactory, DocumentFactory, Generator, register_diagram, register_document

__all__ = [
    "DiagramFactory",
    "DocumentFactory",
    "Generator",
    "Param",
    "Spec",
    "register_diagram",
    "register_document",
]
