"""Find the environmental claims in a report's text chunks and score how specific each is.

chunk text -> candidate sentences -> claim classifier -> keep P(claim) >= threshold
           -> specificity classifier on the kept sentences -> prominence weight

Note: the specificity model is trained on paragraphs but scores single sentences here.
That domain shift is measured on BRSR claims by the Phase 3 gold set.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import config
from .classifier import TextClassifier, model_exists
from .sentences import Sentence, split_sentences

log = logging.getLogger(__name__)

# How prominent a claim is, by where it appears. Section B holds the director's statement
# and the company's headline commitments, which readers see first; the risk score in
# Phase 3 weights claims by this. Everything else counts once.
SECTION_PROMINENCE = {"B": 1.5}


def prominence(section: str | None) -> float:
    return SECTION_PROMINENCE.get(section or "", 1.0)


@dataclass(frozen=True)
class Claim:
    chunk_id: int
    sentence: Sentence
    claim_score: float
    specificity_score: float
    prominence: float


class ClaimExtractor:
    def __init__(self, claim_dir: Path, specificity_dir: Path, threshold: float):
        self.claims = TextClassifier(claim_dir)
        self.specificity = TextClassifier(specificity_dir)
        self.threshold = threshold

    @property
    def model_name(self) -> str:
        return f"{self.claims.name}+{self.specificity.name}@{self.threshold:g}"

    def extract(self, chunks: Sequence[dict]) -> list[Claim]:
        """chunks: dicts with id, text and section (rows from db.text_chunks)."""
        candidates = [(c, s) for c in chunks for s in split_sentences(c["text"])]
        if not candidates:
            return []
        claim_p = self.claims.predict_proba([s.text for _, s in candidates])
        kept = [(c, s, float(p)) for (c, s), p in zip(candidates, claim_p) if p >= self.threshold]
        if not kept:
            return []
        spec_p = self.specificity.predict_proba([s.text for _, s, _ in kept])
        return [Claim(c["id"], s, p, float(sp), prominence(c.get("section")))
                for (c, s, p), sp in zip(kept, spec_p)]


def load_extractor() -> ClaimExtractor | None:
    """None (with a warning) when the models have not been trained yet."""
    missing = [d for d in (config.CLAIM_MODEL_DIR, config.SPECIFICITY_MODEL_DIR) if not model_exists(d)]
    if missing:
        log.warning("No fine-tuned model in %s; claims will not be extracted. "
                    "Train them with: python -m scripts.train_classifier --task claims|specificity",
                    ", ".join(map(str, missing)))
        return None
    return ClaimExtractor(config.CLAIM_MODEL_DIR, config.SPECIFICITY_MODEL_DIR, config.CLAIM_THRESHOLD)
