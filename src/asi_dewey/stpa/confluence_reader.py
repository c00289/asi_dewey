"""Read an STPA Confluence page (its Markdown body) into the plain dataset the STPA factory loads.

Pure functions over asi_hopper's page anatomy (``sections``, ``tables``, ``strike``, ``split_on_bold``,
``links``): the reader knows what an STPA page says, Hopper knows what Markdown is, and neither sees
raw Atlassian JSON (asi_hopper/docs/confluence-integration-plan.md, section 7.3). It takes the body
plus the citation context (page id, URL, version) and answers ``{analysis, losses, hazards, ucas,
scenarios, constraints, warnings}``; every object carries ``cite``:
``page <id> v<version> § <heading> (<url>#<anchor>)``.

The Markdown the MCP server renders flattens cell formatting: bold runs are glued to their text
(``**UCA1 **When the vehicle...``), line breaks inside a cell vanish, strikethrough wraps fragments
and brackets arrive escaped (``*\\[H1, H2\\]*``). The reader works on that text as it is:

- **Losses and hazards**: in the section whose heading contains "Losses and Hazards", one line each,
  ``H2 - text`` or ``L1 - text``; a struck line is retired; a dotted code's parent is the code before
  its last dot when that hazard is listed. A page without losses gets a warning.
- **UCAs**: the first table of the section whose heading contains "Context Table": column 0 the
  controller (carried down when empty), column 1 the control action, columns 2 to 5 the four
  categories in the table's order. Each cell is cut at its bold runs; a run is a UCA code with the
  text that follows it up to the hazard list ``[H1, H2.1]``; a code inside a ``~~`` span is retired;
  ``(duplicate of **UCA7**)`` makes UCA7 the previous UCA's ``duplicate_of``, not a UCA; a cell that
  is a link to another page is a warning naming that page.
- **Scenarios and constraints**: the first table of the section whose heading contains "Loss
  Scenarios": the row number, the UCA or its safe counterpart ``CAn`` at the start of the UCA cell,
  the types from ``Type (\\d)``, the causal factors, the beliefs (``Belief:`` runs), and in the
  constraints cell every ``CSTRn`` with the text that follows it; ``**CSTR1 **and **CSTR2**`` are
  references; a constraint spelled out once keeps that text wherever else it is referenced.
"""

from __future__ import annotations

import re
from typing import Any

from asi_hopper.model.pagetext import Section, find_section, links, sections, split_on_bold, strike, tables

HAZARDS_HEADING = "Losses and Hazards"
CONTEXT_HEADING = "Context Table"
SCENARIOS_HEADING = "Loss Scenarios"
CATEGORIES = ("not_providing", "providing", "timing_order", "duration")  # the four columns, in order

_LINE_CODE = re.compile(r"^\**\s*([HL]\d+(?:\.\d+)*)\s*\**\s*[-–—:]\s*(.+?)\s*$")
_UCA_CODE = re.compile(r"^(UCA\d+)\b")
_UCA_OR_CA = re.compile(r"^\**\s*((?:UCA|CA)\d+)\b")
_CSTR_CODE = re.compile(r"^(CSTR\d+)\b")
_CODE_LIST = re.compile(r"\*?\\?\[([^\]\\]*)\\?\]\*?")  # *\[H1, H2.1\]* or [H1]
_DUPLICATE = re.compile(r"\(\s*duplicate of\s*$", re.IGNORECASE)
_TYPE = re.compile(r"Type\s*(\d)")
_STRUCK = re.compile(r"~~(.+?)~~", re.DOTALL)
_STARS = re.compile(r"\*+")


def cite(page_id: str, version: int | None, section: Section | None, url: str) -> str:
    """``page <id> v<version> § <heading> (<url>#<anchor>)``; without a section, the page alone."""
    head = f"page {page_id} v{version}" if version is not None else f"page {page_id}"
    if section is None or not section.heading:
        return f"{head} ({url})" if url else head
    where = f"{url}#{section.anchor}" if url else section.anchor
    return f"{head} § {section.heading} ({where})"


def codes_in(text: str) -> list[str]:
    """Every code inside bracket lists in ``text`` (``*\\[H1, H2.1\\]*`` gives ``["H1", "H2.1"]``)."""
    out: list[str] = []
    for match in _CODE_LIST.finditer(text or ""):
        for part in match.group(1).split(","):
            code = part.strip().strip("*").strip()
            if code and code not in out:
                out.append(code)
    return out


def without_codes(text: str) -> str:
    """``text`` with its bracket lists, a trailing ``(duplicate of`` and stray stars removed."""
    clean = _CODE_LIST.sub(" ", text or "")
    clean = _DUPLICATE.sub("", clean.strip())
    clean = _STARS.sub("", clean)
    return " ".join(clean.split()).strip(" .,;") + ("." if clean.strip().endswith(".") else "")


def struck_codes(raw: str, pattern: re.Pattern[str]) -> set[str]:
    """The codes that sit inside a ``~~...~~`` span of ``raw``."""
    found: set[str] = set()
    for match in _STRUCK.finditer(raw or ""):
        found.update(pattern.findall(match.group(1)))
    return found


def _plain(text: str) -> str:
    return " ".join(_STARS.sub("", text or "").split())


# -- losses and hazards ----------------------------------------------------------------------------
def read_hazards(section: Section | None, context: dict[str, Any]) -> tuple[list[dict], list[dict], list[str]]:
    """``(losses, hazards, warnings)`` from the lines of the hazards section."""
    losses: list[dict[str, Any]] = []
    hazards: list[dict[str, Any]] = []
    warnings: list[str] = []
    if section is None:
        return losses, hazards, [f"no section whose heading contains {HAZARDS_HEADING!r}"]
    where = cite(context["page_id"], context.get("version"), section, context.get("url") or "")
    for line in section.text.splitlines():
        clean, struck = strike(line)
        match = _LINE_CODE.match(clean.strip())
        if not match:
            continue
        code, text = match.group(1), match.group(2)
        listed = codes_in(text)
        entry = {"code": code, "text": without_codes(text), "cite": where}
        if code.startswith("L"):
            entry["order"] = len(losses) + 1
            losses.append(entry)
        else:
            entry.update({"order": len(hazards) + 1, "parent": "", "losses": listed, "retired": struck})
            hazards.append(entry)
    known = {h["code"] for h in hazards}
    for h in hazards:
        if "." in h["code"]:
            above = h["code"].rsplit(".", 1)[0]
            h["parent"] = above if above in known else ""
    if not hazards:
        warnings.append(f"{section.heading}: no hazard lines (H1 - text) found")
    if not losses:
        warnings.append(f"{section.heading}: no losses listed (L1 - text); losses stay empty")
    return losses, hazards, warnings


# -- the context table: UCAs ------------------------------------------------------------------------
def read_ucas(section: Section | None, context: dict[str, Any], hazard_codes: set[str]) -> tuple[list[dict], list[str]]:
    """``(ucas, warnings)`` from the first table of the context-table section."""
    ucas: list[dict[str, Any]] = []
    warnings: list[str] = []
    if section is None:
        return ucas, [f"no section whose heading contains {CONTEXT_HEADING!r}"]
    found = tables(section.text)
    if not found:
        return ucas, [f"{section.heading}: no table"]
    table = found[0]
    if table.width < 6:
        warnings.append(
            f"{section.heading}: the table has {table.width} columns, six expected (controller, "
            f"control action, {', '.join(CATEGORIES)})"
        )
    where = cite(context["page_id"], context.get("version"), section, context.get("url") or "")
    controller = ""
    for number, row in enumerate(table.rows, start=1):
        controller = _plain(row[0]) or controller
        action = _plain(row[1]) if len(row) > 1 else ""
        for offset, category in enumerate(CATEGORIES):
            index = 2 + offset
            if index >= len(row) or not row[index].strip():
                continue
            raw = row[index]
            clean, _ = strike(raw)
            pieces = split_on_bold(clean)
            if not any(label for label, _ in pieces):
                linked = links(raw)
                if linked:
                    names = ", ".join(
                        f"page {li.page_id} ({li.label})" if li.page_id else f"{li.label} ({li.url})" for li in linked
                    )
                    warnings.append(
                        f"{section.heading} row {number} ({controller} / {action}): the {category} cell links to "
                        f"{names}; that page is its own analysis, no UCA read"
                    )
                    continue
            retired = struck_codes(raw, _UCA_CODE_ANYWHERE)
            previous: dict[str, Any] | None = None
            for label, text in pieces:
                code = ""
                body = text
                if label:
                    match = _UCA_CODE.match(_plain(label))
                    if match:
                        code = match.group(1)
                else:
                    match = _UCA_CODE.match(_plain(text))
                    if match:
                        code = match.group(1)
                        body = _plain(text)[match.end() :]
                if not code:
                    warnings.append(
                        f"{section.heading} row {number} ({controller} / {action}): {category} cell text without a "
                        f"UCA code: {_plain(text)[:60]!r}"
                    )
                    continue
                if previous is not None and _DUPLICATE.search(previous["_raw"].strip()):
                    previous["duplicate_of"] = code  # ``(duplicate of **UCA7**)`` names the previous UCA's twin
                    previous["_raw"] = ""
                    continue
                listed = codes_in(body)
                for h in listed:
                    if h not in hazard_codes:
                        warnings.append(f"{code}: cites hazard {h}, which the page does not list")
                entry = {
                    "order": len(ucas) + 1,
                    "code": code,
                    "controller": controller,
                    "control_action": action,
                    "category": category,
                    "text": without_codes(body),
                    "hazards": listed,
                    "retired": code in retired,
                    "duplicate_of": "",
                    "cite": where,
                    "_raw": body,
                }
                ucas.append(entry)
                previous = entry
    for u in ucas:
        u.pop("_raw", None)
    if not ucas:
        warnings.append(f"{section.heading}: no UCAs read")
    return ucas, warnings


_UCA_CODE_ANYWHERE = re.compile(r"(UCA\d+)")


# -- the loss-scenario table: scenarios and constraints ---------------------------------------------
def read_beliefs(type_cell: str) -> list[str]:
    """The ``Belief:`` runs of a Type cell (``*Belief:**text.***Type 2: **...``), in order."""
    out: list[str] = []
    for part in re.split(r"Belief:", type_cell or "")[1:]:
        text = re.split(r"\*\*\s*Type\s*\d", part)[0]
        text = _plain(text)
        if text:
            out.append(text)
    return out


def read_constraint_cell(raw: str) -> list[tuple[str, str]]:
    """``[(code, text)]`` for every CSTR in a constraints cell; a reference has an empty text."""
    clean, _ = strike(raw)
    out: list[tuple[str, str]] = []
    for label, text in split_on_bold(clean):
        code = ""
        body = _plain(text)
        match = _CSTR_CODE.match(_plain(label)) if label else None
        if match:
            code = match.group(1)
        else:
            match = _CSTR_CODE.match(body)
            if match:
                code = match.group(1)
                body = body[match.end() :].strip()
        if not code:
            continue
        if body.casefold() in ("and", "and.", ",", ";", "&"):
            body = ""
        body = re.sub(r"\s+and$", "", body).strip()
        out.append((code, body))
    return out


def read_scenarios(
    section: Section | None, context: dict[str, Any], uca_codes: set[str]
) -> tuple[list[dict], list[dict], list[str]]:
    """``(scenarios, constraints, warnings)`` from the first table of the loss-scenario section."""
    scenarios: list[dict[str, Any]] = []
    constraints: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    if section is None:
        return scenarios, [], [f"no section whose heading contains {SCENARIOS_HEADING!r}"]
    found = tables(section.text)
    if not found:
        return scenarios, [], [f"{section.heading}: no table"]
    table = found[0]
    where = cite(context["page_id"], context.get("version"), section, context.get("url") or "")
    for number, row in enumerate(table.rows, start=1):
        cells = list(row) + [""] * (5 - len(row))
        try:
            row_number = int(_plain(cells[0]))
        except ValueError:
            row_number = number
        uca_clean, struck = strike(cells[1])
        pieces = split_on_bold(uca_clean)
        head = ""
        if pieces:
            label, text = pieces[0]
            head = _plain(label) if label else _plain(text)
        match = _UCA_OR_CA.match(head)
        uca, counterpart = "", ""
        if match:
            code = match.group(1)
            if code.startswith("CA"):
                counterpart, uca = code, "UCA" + code[2:]
            else:
                uca = code
        elif head:
            warnings.append(
                f"{section.heading} row {row_number}: UCA cell starts with {head[:40]!r}, no UCA or CA code"
            )
        else:
            warnings.append(f"{section.heading} row {row_number}: empty UCA cell; the row is kept without a UCA")
        if uca and uca not in uca_codes:
            warnings.append(f"{section.heading} row {row_number}: {uca} is not in the context table")
        types: list[int] = []
        for t in _TYPE.findall(strike(cells[2])[0]):
            if int(t) not in types:
                types.append(int(t))
        cstr = read_constraint_cell(cells[4])
        for code, text in cstr:
            entry = constraints.setdefault(
                code,
                {"order": len(constraints) + 1, "code": code, "text": "", "cite": where},
            )
            if text and not entry["text"]:
                entry["text"] = text  # the first row that spells it out wins
        scenarios.append(
            {
                "order": len(scenarios) + 1,
                "row": row_number,
                "uca": uca,
                "counterpart": counterpart,
                "types": types,
                "causal_factors": _plain(strike(cells[3])[0]),
                "beliefs": "\n".join(read_beliefs(strike(cells[2])[0])),
                "constraints": [c for c, _ in cstr],
                "retired": struck,
                "cite": where,
            }
        )
    if not scenarios:
        warnings.append(f"{section.heading}: no scenario rows read")
    return scenarios, list(constraints.values()), warnings


# -- the whole page -----------------------------------------------------------------------------------
def read_stpa_page(
    markdown: str, *, page_id: str, url: str = "", version: int | None = None, title: str = ""
) -> dict[str, Any]:
    """The dataset of one STPA page: ``analysis`` (name, system, the ``source_*`` the body says), the five
    object lists and ``warnings``. Pure: nothing is read but ``markdown`` and the context given."""
    context = {"page_id": str(page_id), "url": url or "", "version": version}
    found = sections(markdown or "")
    losses, hazards, w1 = read_hazards(find_section(found, HAZARDS_HEADING), context)
    ucas, w2 = read_ucas(find_section(found, CONTEXT_HEADING), context, {h["code"] for h in hazards})
    scenarios, constraints, w3 = read_scenarios(
        find_section(found, SCENARIOS_HEADING),
        context,
        {u["code"] for u in ucas},
    )
    for u in ucas:
        if u["duplicate_of"] and u["duplicate_of"] not in {x["code"] for x in ucas}:
            w2.append(f"{u['code']}: duplicate of {u['duplicate_of']}, which the context table does not list")
    return {
        "analysis": {
            "name": title or f"page {page_id}",
            "system": "",
            "source_kind": "confluence",
            "source_page_id": str(page_id),
            "source_url": url or None,
            "source_version": version,
        },
        "losses": losses,
        "hazards": hazards,
        "ucas": ucas,
        "scenarios": scenarios,
        "constraints": constraints,
        "warnings": [*w1, *w2, *w3],
        "sections": [s.heading for s in found if s.heading],
    }


__all__ = [
    "CATEGORIES",
    "cite",
    "codes_in",
    "read_beliefs",
    "read_constraint_cell",
    "read_hazards",
    "read_scenarios",
    "read_stpa_page",
    "read_ucas",
    "without_codes",
]
