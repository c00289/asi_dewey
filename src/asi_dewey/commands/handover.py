"""The ``handover`` verb: the STPA work explored here, written out for asi_kletz (``asi_dewey.handover``).

``handover [--out <dir>]`` reads the thirteen tables of 0.9.0 to 0.10.1 that an older database still holds
(unregistered since 0.11.0, never dropped) and writes ``dewey-stpa.json`` for ``asi-kletz load``, one
datasets folder per control structure for ``asi-kletz cs new from_datasets``, a copy of every evidence
bundle still on this machine for ``asi-kletz stpa new from_bundle``, the thirteen-sheet workbook and a
manifest with the Kletz command lines. Nothing is deleted. The Result lists the counts, the files and
the commands; a database with nothing to hand over is a failed Result.
"""

from __future__ import annotations

from typing import Any

from ..handover import DEFAULT_DIR, write_handover
from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class HandoverCommand(Command):
    verb = "handover"
    help = (
        "Write the STPA work explored here (the control structures and STPA analyses of 0.9.0 to 0.10.1) in the "
        "files asi_kletz reads: --out <dir> (default: handover/ under the out folder). Nothing is deleted."
    )
    arguments = (
        Argument("out", f"Output folder (default: {DEFAULT_DIR}/ under the out folder)", flag=True, type="path"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        data, warnings = write_handover(ctx.brain, args.get("out"), ctx.actor)
        return Result.success(data, warnings)
