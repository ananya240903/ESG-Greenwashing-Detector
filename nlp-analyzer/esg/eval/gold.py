"""The BRSR gold set: claims hand-labelled with a verdict and the passages that back them.

Files (committed):
  eval/gold/items.jsonl   what was shown to the labeller: claim, context, pooled passages
  eval/gold/labels.jsonl  the labeller's answers, one line per save (the last one per key wins)
  eval/gold/labels_pass2.jsonl  a second, slower pass over the test split's claims, with a
                          stricter guide and the first answers hidden. Where it exists it
                          replaces the first pass, and the two are compared for consistency.

An item's key is "<company>|<fiscal year>|<chunk seq>|<char start>", which survives
re-parsing (claim and chunk ids do not). Passages are identified by chunk seq.

Each item is in the dev split (used to tune thresholds) or the test split (used to report
numbers), decided by a hash of its key so the split never changes.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

GOLD_DIR = Path("eval/gold")
ITEMS = GOLD_DIR / "items.jsonl"
LABELS = Path(os.getenv("GOLD_LABELS", str(GOLD_DIR / "labels.jsonl")))  # overridable for testing
LABELS_PASS2 = Path(os.getenv("GOLD_LABELS_PASS2", str(GOLD_DIR / "labels_pass2.jsonl")))
VERDICTS = ("substantiated", "vague", "unsupported")
DEV_FRACTION = 0.4


def item_key(company: str, fiscal_year: int, chunk_seq: int, char_start: int) -> str:
    return f"{company}|{fiscal_year}|{chunk_seq}|{char_start}"


def split_of(key: str) -> str:
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "dev" if h < DEV_FRACTION else "test"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def append_label(label: dict, path: Path = LABELS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(label, ensure_ascii=False) + "\n")


def latest_labels(path: Path = LABELS) -> dict[str, dict]:
    out = {}
    for row in read_jsonl(path):
        out[row["key"]] = row
    return out


@dataclass(frozen=True)
class GoldClaim:
    key: str
    split: str
    company: str
    fiscal_year: int
    chunk_seq: int
    char_start: int
    char_end: int
    sentence: str
    is_claim: bool
    verdict: str | None              # None when is_claim is False
    supporting_seqs: frozenset[int]  # chunk seqs of passages that back the claim
    judged_seqs: frozenset[int]      # every passage that was shown (the judging pool)


def second_pass_keys(items_path: Path = ITEMS, labels_path: Path = LABELS) -> list[str]:
    """The items re-labelled in the second pass: test-split items the first pass called claims."""
    first = latest_labels(labels_path)
    return [it["key"] for it in read_jsonl(items_path)
            if split_of(it["key"]) == "test" and first.get(it["key"], {}).get("is_claim")]


def load_gold(items_path: Path = ITEMS, labels_path: Path = LABELS,
              overrides_path: Path | None = None) -> list[GoldClaim]:
    """Labelled items; answers in overrides_path (the second pass) replace the first pass."""
    labels = latest_labels(labels_path)
    if overrides_path is not None:
        labels.update(latest_labels(overrides_path))
    out = []
    for item in read_jsonl(items_path):
        label = labels.get(item["key"])
        if label is None:
            continue
        by_pid = {p["pid"]: p["chunk_seq"] for p in item["passages"]}
        out.append(GoldClaim(
            key=item["key"], split=split_of(item["key"]), company=item["company"],
            fiscal_year=item["fiscal_year"], chunk_seq=item["chunk_seq"],
            char_start=item["char_start"], char_end=item["char_end"], sentence=item["sentence"],
            is_claim=label["is_claim"], verdict=label.get("verdict") if label["is_claim"] else None,
            supporting_seqs=frozenset(by_pid[p] for p in label.get("supporting", ()) if p in by_pid),
            judged_seqs=frozenset(by_pid.values()),
        ))
    return out
