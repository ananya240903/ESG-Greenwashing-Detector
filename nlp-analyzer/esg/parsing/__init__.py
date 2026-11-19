from __future__ import annotations

from pathlib import Path

from .chunker import chunk
from .types import Chunk, Element


def parse_pdf(path: str | Path, find_tables: bool = True) -> tuple[int, list[Chunk]]:
    """Parse a BRSR PDF into section-aware chunks. Returns (page_count, chunks)."""
    from .pdf import extract  # imported here so the pure-Python parts load without PyMuPDF

    parsed = extract(path, find_tables=find_tables)
    return parsed.page_count, chunk(parsed.elements)


__all__ = ["Chunk", "Element", "chunk", "parse_pdf"]
