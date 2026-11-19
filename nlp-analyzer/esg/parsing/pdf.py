"""Turn a PDF into an ordered list of text blocks and tables, using PyMuPDF."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

from .sections import PRINCIPLE_RE, SECTION_RE
from .types import Element

# A line that recurs on at least this share of pages is a running header/footer.
REPEATED_LINE_SHARE = 0.4
MIN_PAGES_FOR_REPEAT_FILTER = 5


@dataclass
class ParsedPdf:
    page_count: int
    elements: list[Element]


def _clean_cell(cell: str | None) -> str:
    return " ".join((cell or "").split())


def _normalise_for_repeat(line: str) -> str:
    # Page numbers change from page to page, so ignore digits when spotting repeats.
    return re.sub(r"\d+", "#", " ".join(line.split()).lower())


def _overlaps(a: fitz.Rect, b: fitz.Rect, min_share: float = 0.5) -> bool:
    inter = a & b
    return not inter.is_empty and inter.get_area() >= min_share * max(a.get_area(), 1e-6)


def extract(path: str | Path, find_tables: bool = True) -> ParsedPdf:
    doc = fitz.open(path)
    elements: list[Element] = []

    for page in doc:
        page_no = page.number + 1
        table_rects: list[fitz.Rect] = []

        if find_tables:
            try:
                tables = page.find_tables().tables
            except Exception:  # malformed page; fall back to text only
                tables = []
            for t in tables:
                rows = [[_clean_cell(c) for c in row] for row in t.extract()]
                rows = [r for r in rows if any(r)]
                if len(rows) < 2:      # a one-row "table" is usually a layout box
                    continue
                rect = fitz.Rect(t.bbox)
                table_rects.append(rect)
                elements.append(Element("table", page_no, rect.y0, rows=rows))

        for x0, y0, x1, y1, text, _no, block_type in page.get_text("blocks", sort=True):
            if block_type != 0:  # image block
                continue
            rect = fitz.Rect(x0, y0, x1, y1)
            if any(_overlaps(rect, tr) for tr in table_rects):
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if lines:
                elements.append(Element("text", page_no, y0, lines=lines))

    page_count = doc.page_count
    doc.close()

    elements.sort(key=lambda e: (e.page, e.y0))
    return ParsedPdf(page_count, _drop_running_lines(elements, page_count))


def _drop_running_lines(elements: list[Element], page_count: int) -> list[Element]:
    if page_count < MIN_PAGES_FOR_REPEAT_FILTER:
        return elements

    lines_by_page: dict[int, set[str]] = defaultdict(set)
    for e in elements:
        if e.kind == "text":
            lines_by_page[e.page].update(_normalise_for_repeat(ln) for ln in e.lines)
    pages_with: Counter[str] = Counter()
    for seen in lines_by_page.values():
        pages_with.update(seen)
    threshold = REPEATED_LINE_SHARE * page_count
    running = {k for k, n in pages_with.items() if n >= threshold}

    def keep(line: str) -> bool:
        # Section/principle headings often double as running headers. Keep them:
        # section detection is forward-only, so the repeats are harmless.
        if SECTION_RE.match(line) or PRINCIPLE_RE.match(line):
            return True
        return _normalise_for_repeat(line) not in running

    kept: list[Element] = []
    for e in elements:
        if e.kind == "text":
            e.lines = [ln for ln in e.lines if keep(ln)]
            if not e.lines:
                continue
        kept.append(e)
    return kept
