"""Words versus numbers: do the figures in a claim appear elsewhere in the report?

NLI models read prose and handle tables of figures poorly, yet BRSR evidence is mostly
tables. This check needs no model: it pulls the figures out of a claim ("94%", "39 million",
"2,928.07", "3,80,000") and looks for the same figures in the report's other passages.

Not counted as figures: bare years (2030, FY 2023-24), and small whole numbers without a
unit ("Scope 1", "Principle 6", "4-step"), which match by accident far too often.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_SCALE = {"thousand": "k", "lakh": "lakh", "lakhs": "lakh", "crore": "cr", "crores": "cr", "cr": "cr",
          "million": "m", "mn": "m", "billion": "bn", "bn": "bn"}
_NUMBER = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d+))?"           # 94 | 2,928 | 3,80,000 | 2928.07
    r"(?:\s*(%|per\s*cent|percent))?"                               # 94% | 94 per cent
    r"(?:\s*(thousand|lakhs?|crores?|cr|million|mn|billion|bn)\b)?",  # 39 million | 1,200 crore
    re.IGNORECASE)


@dataclass(frozen=True)
class Figure:
    text: str      # as written in the claim
    key: str       # canonical form used for matching, e.g. "94%" or "39m"


def figures(text: str) -> list[Figure]:
    out, seen = [], set()
    for m in _NUMBER.finditer(text):
        whole, frac, pct, scale = m.groups()
        digits = whole.replace(",", "")
        value = float(f"{digits}.{frac}" if frac else digits)
        is_pct, unit = pct is not None, _SCALE.get((scale or "").lower(), "")
        prev = text[max(0, m.start() - 1):m.start()]
        if not is_pct and not unit and not frac:
            if 1900 <= value <= 2100:
                continue                       # a year
            if prev in "-–/" and m.start() > 0:
                continue                       # the "24" of "2023-24"
            if value < 10:
                continue                       # "Scope 1", "4-step"
        key = f"{value:g}{'%' if is_pct else ''}{unit}"
        if key not in seen:
            seen.add(key)
            out.append(Figure(m.group(0).strip(), key))
    return out


@dataclass(frozen=True)
class NumberCheck:
    figures: tuple[str, ...]                  # the claim's figures, as written
    found_in: tuple[int | None, ...]          # for each, a chunk id where it appears, or None
    found_labels: tuple[str | None, ...] = ()  # and that passage's label, e.g. "table, Principle 6, p. 31"

    @property
    def has_figures(self) -> bool:
        return bool(self.figures)

    @property
    def all_found(self) -> bool:
        return self.has_figures and all(c is not None for c in self.found_in)

    @property
    def none_found(self) -> bool:
        return self.has_figures and all(c is None for c in self.found_in)


def check(claim: str, passages: Iterable[tuple[int, str, str]]) -> NumberCheck:
    """passages: (chunk_id, label, text) to search, with the claim itself already cut out."""
    wanted = figures(claim)
    if not wanted:
        return NumberCheck((), ())
    where: dict[str, tuple[int, str]] = {}
    for chunk_id, label, text in passages:
        for f in figures(text):
            where.setdefault(f.key, (chunk_id, label))
        if all(w.key in where for w in wanted):
            break
    hits = [where.get(f.key) for f in wanted]
    return NumberCheck(tuple(f.text for f in wanted), tuple(h[0] if h else None for h in hits),
                       tuple(h[1] if h else None for h in hits))
