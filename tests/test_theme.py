"""The family palette catalog, the theme factory, theme resolution, and the preference file."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from asi_dewey.errors import NotFound
from asi_dewey.gui import palettes
from asi_dewey.gui.palettes import CATALOG, CATALOG_DIGEST, FAMILIES, TONES
from asi_dewey.gui.theme import DEFAULT_THEME, ENV_THEME, GridTheme, Theme, ThemeFactory, TronTheme
from asi_dewey.prefs import ENV_PREFS, TOOL, prefs_path, read_prefs, write_prefs
from asi_dewey.version import __version__

SLOTS = (
    "bg", "panel", "field", "grid", "stripe", "primary", "primary_dim", "accent", "text", "muted",
    "on_primary", "selection",
)
PLAN_DIGEST = "befcfc0c8dca5479620badf1d23e2448db757910"  # section 3.1 of docs/theme-palette-plan.md
FAMILY_FILE = Path(__file__).resolve().parents[2] / "asi_fusa_tools" / "ASI_FUSA_TOOLS.md"
HEX = re.compile(r"#[0-9a-f]{6}")


# -- catalog --------------------------------------------------------------
def test_catalog_has_32_entries_in_family_then_tone_order():
    assert len(FAMILIES) == 8 and len(TONES) == 4
    assert list(CATALOG) == [f"{family}-{tone}" for family in FAMILIES for tone in TONES]
    for key, entry in CATALOG.items():
        family, tone = key.split("-")
        assert (entry.family, entry.tone) == (family, tone)
        assert entry.title == f"{family.capitalize()} {tone.capitalize()}"
        for slot in SLOTS:
            value = getattr(entry.palette, slot)
            assert HEX.fullmatch(value), f"{key}.{slot} = {value!r}"
    assert len({entry.palette.primary for entry in CATALOG.values()}) == 32
    assert CATALOG["pink-noir"].title == "Pink Noir" and CATALOG["pink-day"].title == "Pink Day"


def test_catalog_digest_matches_the_family_convention():
    payload = {key: {slot: getattr(entry.palette, slot) for slot in SLOTS} for key, entry in CATALOG.items()}
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    assert digest == CATALOG_DIGEST == PLAN_DIGEST
    if FAMILY_FILE.exists():  # the authority; absent when the repo is tested on its own
        text = FAMILY_FILE.read_text(encoding="utf-8")
        assert text.splitlines()[0] == "# ASI FuSa Tools"  # the charter, not a stale copy under the old name
        assert CATALOG_DIGEST in text


def _luminance(colour: str) -> float:
    channels = []
    for i in (1, 3, 5):
        c = int(colour[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("key", list(CATALOG))
def test_every_palette_meets_the_contrast_floors(key):
    p = CATALOG[key].palette
    for fg, bg in (
        (p.text, p.bg), (p.text, p.field), (p.primary, p.panel), (p.primary, p.bg),
        (p.on_primary, p.primary), (p.on_primary, p.accent),
    ):
        assert contrast(fg, bg) >= 4.5, f"{key}: {fg} on {bg} = {contrast(fg, bg):.2f}"
    for fg, bg in (
        (p.muted, p.bg), (p.muted, p.panel), (p.accent, p.panel), (p.text, p.selection), (p.primary_dim, p.bg),
    ):
        assert contrast(fg, bg) >= 3.0, f"{key}: {fg} on {bg} = {contrast(fg, bg):.2f}"


def test_palettes_module_imports_only_palette_and_typing():
    tree = ast.parse(Path(palettes.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert [alias.name for alias in node.names] == ["typing"], ast.dump(node)
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            assert (node.module, node.level, names) in (("typing", 0, ["NamedTuple"]), ("theme", 1, ["Palette"])), (
                ast.dump(node)
            )


# -- factory --------------------------------------------------------------
def test_factory_registers_catalog_alias_and_plain():
    keys = ThemeFactory.keys()
    assert set(keys) >= set(CATALOG) | {"tron", "plain"} and len(keys) == 34
    assert keys[:32] == list(CATALOG) and keys[32:] == ["tron", "plain"]
    tron = ThemeFactory.create("tron")
    assert tron.key == "cyan-neon" and type(tron) is TronTheme and isinstance(tron, GridTheme)
    assert ThemeFactory.get("tron") is ThemeFactory.get("cyan-neon")
    plain = ThemeFactory.create("plain")
    assert plain.key == "plain" and type(plain) is Theme and not isinstance(plain, GridTheme)
    entries = ThemeFactory.entries()
    assert [e.key for e in entries] == list(CATALOG)
    assert all(e.key not in ("tron", "plain") for e in entries)
    assert entries[0].title == "Cyan Noir" and entries[0].palette is CATALOG["cyan-noir"].palette
    with pytest.raises(NotFound):
        ThemeFactory.create("neon-pink")
    assert ThemeFactory.default_key() == DEFAULT_THEME == "cyan-neon"
    for key in CATALOG:
        assert ThemeFactory.create(key).palette == CATALOG[key].palette


def test_resolve_precedence(monkeypatch):
    assert ThemeFactory.resolve(None) == "cyan-neon"
    assert ThemeFactory.latched() == (None, None)
    write_prefs(theme="pink-noir")
    assert ThemeFactory.resolve(None) == "pink-noir" and ThemeFactory.latched() == ("pink-noir", None)
    monkeypatch.setenv(ENV_THEME, "green-day")
    assert ThemeFactory.resolve(None) == "green-day"
    assert ThemeFactory.resolve("plain") == "plain"
    monkeypatch.delenv(ENV_THEME)
    write_prefs(theme="sepia")
    assert ThemeFactory.resolve(None) == "cyan-neon"
    latched, warning = ThemeFactory.latched()
    assert latched is None and "sepia" in warning


# -- prefs ----------------------------------------------------------------
def test_prefs_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "state" / "asi" / "dewey" / "prefs.json"
    monkeypatch.setenv(ENV_PREFS, str(path))
    assert prefs_path() == path
    assert read_prefs() == {}
    assert write_prefs(theme="red-dusk") == path and path.is_file()
    data = read_prefs()
    assert data["theme"] == "red-dusk" and data["tool"] == TOOL and data["version"] == __version__
    assert data["updated_at"].endswith("+00:00")
    write_prefs(badge=True)
    data = read_prefs()
    assert data["theme"] == "red-dusk" and data["badge"] is True  # a second write merges

    path.write_text("{not json", encoding="utf-8")
    assert read_prefs() == {}
    write_prefs(theme="gold-day")
    assert read_prefs()["theme"] == "gold-day" and "badge" not in read_prefs()  # replaced, not merged with junk
    path.write_text("[1, 2]", encoding="utf-8")
    assert read_prefs() == {}  # not an object
    assert not list(path.parent.glob("*.tmp"))  # the temp file was replaced into place


def test_prefs_path_without_override(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_PREFS, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    base = tmp_path / ("local" if os.name == "nt" else "xdg")
    assert prefs_path() == base / "asi" / "dewey" / "prefs.json"
