from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Element:
    """One piece of a PDF page, in reading order."""
    kind: str                    # 'text' or 'table'
    page: int                    # 1-based
    y0: float                    # top edge, for reading order
    lines: list[str] = field(default_factory=list)       # text: the block's lines
    rows: list[list[str]] = field(default_factory=list)  # table: header row first


@dataclass
class Chunk:
    """A retrievable piece of a report; mirrors a row of the `chunks` table."""
    seq: int
    kind: str
    section: str | None
    principle: int | None
    heading: str | None
    page_start: int
    page_end: int
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())
