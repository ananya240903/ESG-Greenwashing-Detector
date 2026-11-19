"""Detect where BRSR sections and principles start.

A BRSR has three sections (A: General Disclosures, B: Management and Process
Disclosures, C: Principle-wise Performance Disclosure), and Section C is split
into Principles 1-9, each with Essential and Leadership Indicators.

Detection is line-based and forward-only: a report can move A -> B -> C and
P1 -> P9 but never back. That makes running page headers ("Section C | ...")
and in-text mentions ("see Principle 6") harmless, because they either repeat
the current state or point backwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

SECTION_RE = re.compile(
    r"^\s*SECTION\s*[-:]?\s*([ABC])\b\s*[:.\-–—]?\s*"
    r"(GENERAL|MANAGEMENT|PRINCIPLE)",
    re.IGNORECASE,
)
PRINCIPLE_RE = re.compile(r"^\s*PRINCIPLE\s*[-:]?\s*([1-9])\b", re.IGNORECASE)
INDICATOR_RE = re.compile(r"^\s*(ESSENTIAL|LEADERSHIP)\s+INDICATORS?\b", re.IGNORECASE)
# Table-of-contents lines end in a page number ("Section A: General Disclosures ..... 4").
TOC_TAIL_RE = re.compile(r"(\.{2,}|\s)\d{1,3}\s*$")
MAX_HEADING_CHARS = 200


@dataclass(frozen=True)
class SectionState:
    section: str | None = None   # 'A', 'B', 'C' or None (before the BRSR starts)
    principle: int | None = None
    heading: str | None = None   # 'Essential Indicators' / 'Leadership Indicators'


def _looks_like_toc(rest: str) -> bool:
    """`rest` is the line after the heading keyword. A bare "PRINCIPLE 1" is a heading;
    "PRINCIPLE 1 Businesses should ... 14" is an index entry pointing at page 14."""
    return bool(rest.strip()) and bool(TOC_TAIL_RE.search(rest))


def advance(state: SectionState, line: str) -> SectionState:
    """Return the state after reading `line`. Unchanged if the line is not a new heading."""
    text = line.strip()
    if not text or len(text) > MAX_HEADING_CHARS:
        return state

    m = SECTION_RE.match(text) or PRINCIPLE_RE.match(text)
    if m and _looks_like_toc(text[m.end():]):
        return state

    m = SECTION_RE.match(text)
    if m:
        new = m.group(1).upper()
        if state.section is None or new > state.section:
            return SectionState(section=new)
        return state

    m = PRINCIPLE_RE.match(text)
    if m and state.section == "C":
        p = int(m.group(1))
        if state.principle is None or p > state.principle:
            return SectionState(section="C", principle=p)
        return state

    m = INDICATOR_RE.match(text)
    if m and state.section is not None:
        heading = f"{m.group(1).capitalize()} Indicators"
        if heading != state.heading:
            return replace(state, heading=heading)

    return state
