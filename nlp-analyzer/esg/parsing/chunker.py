"""Group PDF elements into chunks that never cross a BRSR section or principle boundary.

Prose is packed into chunks of roughly TARGET_WORDS. Each table is its own chunk;
a long table is split into row slices that each repeat the header row, so every
table chunk can be read on its own as evidence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .sections import SectionState, advance
from .types import Chunk, Element

TARGET_WORDS = 200
MAX_WORDS = 300
TABLE_MAX_WORDS = 300

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def join_lines(lines: Iterable[str]) -> str:
    """Join wrapped PDF lines into one paragraph, mending words hyphenated across lines."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line
        else:
            out = f"{out} {line}" if out else line
    return out


def split_long(paragraph: str, limit: int = TARGET_WORDS) -> list[str]:
    """Split a paragraph longer than `limit` words at sentence ends (hard-wrap a runaway sentence)."""
    pieces: list[str] = []
    current: list[str] = []
    count = 0
    for sentence in SENTENCE_SPLIT_RE.split(paragraph):
        words = sentence.split()
        while len(words) > limit:  # a single "sentence" longer than the limit (often a list)
            if current:
                pieces.append(" ".join(current))
                current, count = [], 0
            pieces.append(" ".join(words[:limit]))
            words = words[limit:]
        if count + len(words) > limit and current:
            pieces.append(" ".join(current))
            current, count = [], 0
        if words:
            current.append(" ".join(words))
            count += len(words)
    if current:
        pieces.append(" ".join(current))
    return pieces


def render_table(rows: list[list[str]]) -> str:
    def fmt(row: list[str]) -> str:
        return "| " + " | ".join(cell.replace("|", "/") for cell in row) + " |"
    return "\n".join(fmt(r) for r in rows)


def table_slices(rows: list[list[str]], limit: int = TABLE_MAX_WORDS) -> list[list[list[str]]]:
    """Split a table into row groups under `limit` words, each starting with the header row."""
    header, body = rows[0], rows[1:]
    header_words = sum(len(c.split()) for c in header)
    slices: list[list[list[str]]] = []
    current: list[list[str]] = []
    count = header_words
    for row in body:
        row_words = sum(len(c.split()) for c in row)
        if current and count + row_words > limit:
            slices.append([header, *current])
            current, count = [], header_words
        current.append(row)
        count += row_words
    if current or not slices:
        slices.append([header, *current])
    return slices


class _Builder:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.state = SectionState()
        self.buf: list[str] = []
        self.buf_words = 0
        self.buf_pages: tuple[int, int] | None = None

    def _emit(self, kind: str, text: str, pages: tuple[int, int]) -> None:
        s = self.state
        self.chunks.append(Chunk(
            seq=len(self.chunks), kind=kind, section=s.section, principle=s.principle,
            heading=s.heading, page_start=pages[0], page_end=pages[1], text=text,
        ))

    def flush(self) -> None:
        if self.buf and self.buf_pages:
            self._emit("text", "\n".join(self.buf), self.buf_pages)
        self.buf, self.buf_words, self.buf_pages = [], 0, None

    def set_state(self, new: SectionState) -> None:
        if new != self.state:
            self.flush()
            self.state = new

    def add_paragraph(self, text: str, page: int) -> None:
        for piece in split_long(text) if len(text.split()) > MAX_WORDS else [text]:
            words = len(piece.split())
            if self.buf and self.buf_words + words > MAX_WORDS:
                self.flush()
            self.buf.append(piece)
            self.buf_words += words
            start = self.buf_pages[0] if self.buf_pages else page
            self.buf_pages = (start, page)
            if self.buf_words >= TARGET_WORDS:
                self.flush()

    def add_text(self, element: Element) -> None:
        pending: list[str] = []
        for line in element.lines:
            new = advance(self.state, line)
            if new != self.state:
                if pending:
                    self.add_paragraph(join_lines(pending), element.page)
                    pending = []
                self.set_state(new)
            pending.append(line)  # heading lines open the next chunk, as context
        if pending:
            self.add_paragraph(join_lines(pending), element.page)

    def add_table(self, element: Element) -> None:
        self.flush()
        rows = element.rows
        # Some reports draw a principle or section banner as a one-cell table row.
        first_cells = [c for c in rows[0] if c]
        if len(first_cells) == 1:
            new = advance(self.state, first_cells[0])
            if new != self.state:
                self.set_state(new)
                rows = rows[1:]
                if len(rows) < 2:
                    if rows:
                        self.add_paragraph(" ".join(c for c in rows[0] if c), element.page)
                    return
        for group in table_slices(rows):
            self._emit("table", render_table(group), (element.page, element.page))


def chunk(elements: Iterable[Element]) -> list[Chunk]:
    builder = _Builder()
    for element in elements:
        if element.kind == "table":
            builder.add_table(element)
        else:
            builder.add_text(element)
    builder.flush()
    return builder.chunks
