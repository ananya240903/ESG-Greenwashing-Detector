"""Parse BRSR PDFs locally, without Postgres or Kafka, and print what the chunker found.

    python scripts/parse_pdf.py ../data/brsr/*.pdf
    python scripts/parse_pdf.py report.pdf --dump chunks.jsonl   # write every chunk out
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from esg.parsing import parse_pdf  # noqa: E402


def summarise(path: Path, dump: Path | None) -> dict:
    started = time.monotonic()
    page_count, chunks = parse_pdf(path)
    elapsed = time.monotonic() - started

    sections = Counter(c.section or "-" for c in chunks)
    principles = sorted({c.principle for c in chunks if c.principle})
    first_page = {s: min(c.page_start for c in chunks if c.section == s) for s in "ABC"
                  if any(c.section == s for c in chunks)}
    words = [c.word_count for c in chunks]

    if dump:
        with dump.open("a", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps({"file": path.name, **asdict(c)}, ensure_ascii=False) + "\n")

    return {
        "file": path.name,
        "pages": page_count,
        "seconds": round(elapsed, 1),
        "chunks": len(chunks),
        "text": sum(c.kind == "text" for c in chunks),
        "table": sum(c.kind == "table" for c in chunks),
        "by_section": dict(sorted(sections.items())),
        "section_first_page": first_page,
        "principles_found": principles,
        "words_median": sorted(words)[len(words) // 2] if words else 0,
        "words_max": max(words, default=0),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--dump", type=Path, help="append every chunk to this .jsonl file")
    args = ap.parse_args()
    if args.dump and args.dump.exists():
        args.dump.unlink()
    for pdf in args.pdfs:
        print(json.dumps(summarise(pdf, args.dump)))


if __name__ == "__main__":
    main()
