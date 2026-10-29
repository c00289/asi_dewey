"""STPA: the control-structure factory and the draw.io reader (docs/control-structure-plan.md).

``ControlStructureFactory`` (``brain.factory``) builds a structure several ways (``blank``,
``template:wheel_loader_master``, ``from_drawio``, ``from_datasets``, ``clone``) and is the one
place that turns the rows into an ``asi_escher.Diagram`` (``to_diagram``) and writes the files
(``export``). ``drawio_reader.read_drawio`` parses a draw.io file into the plain dataset the
factory loads, standard library only, as the script it was ported from.
"""

from .drawio_reader import read_dataset_folder, read_drawio
from .factory import FORMATS, Builder, ControlStructureFactory, register_builder

__all__ = [
    "FORMATS",
    "Builder",
    "ControlStructureFactory",
    "read_dataset_folder",
    "read_drawio",
    "register_builder",
]
