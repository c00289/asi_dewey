"""The ``theme`` verb: list the family palette, or latch a theme for the window.

Everything the window's picker does, this verb does: with a key it validates it, writes the
preference file, and publishes ``theme.changed`` so a window open in this process repaints.
Without a key (or with ``--list``) it reports the catalog, the latched key, the key that would
paint a window opened now, and where the preference lives.
"""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command


def theme_report() -> dict[str, Any]:
    """The catalog, the latched key, the resolved key, the house default, and the prefs path."""
    from ..gui.theme import ThemeFactory
    from ..prefs import prefs_path, read_prefs

    return {
        "theme": ThemeFactory.resolve(None),
        "latched": read_prefs().get("theme"),
        "default": ThemeFactory.default_key(),
        "prefs": str(prefs_path()),
        "themes": [
            {
                "key": e.key, "title": e.title, "family": e.family, "tone": e.tone,
                "primary": e.palette.primary, "accent": e.palette.accent,
            }
            for e in ThemeFactory.entries()
        ],
    }


@register_command
class ThemeCommand(Command):
    verb = "theme"
    help = "Latch a window theme (no key: list the catalog, the latched key and the preference file)."
    arguments = (
        Argument("key", "Theme key such as pink-noir or plain (omit to list the catalog)"),
        Argument("list", "List the catalog; the same as giving no key", flag=True, type="bool"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        from ..gui.theme import ThemeFactory
        from ..prefs import write_prefs

        key = args.get("key")
        if key:
            ThemeFactory.create(key)  # unknown key: NotFound, which the dispatcher turns into a failure
            write_prefs(theme=key)
            ctx.brain.events.publish("theme.changed", theme=key, actor=ctx.actor)
        return Result.success(theme_report())
