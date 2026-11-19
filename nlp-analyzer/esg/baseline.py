"""The original FinBERT heuristic, kept unchanged as the baseline to beat.

risk = sentiment confidence x (1 - ESG confidence) x 100, and a passage is flagged
when it is both vague (no confident ESG label) and hyped (confidently positive).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from . import config


@dataclass(frozen=True)
class BaselineScore:
    esg_label: str
    esg_score: float
    tone_label: str
    tone_score: float
    risk_score: float
    flagged: bool


def score(esg_label: str, esg_score: float, tone_label: str, tone_score: float) -> BaselineScore:
    risk = tone_score * (1 - esg_score) * 100
    is_vague = esg_label == "None" or esg_score < 0.7
    is_hyped = tone_label.lower() == "positive" and tone_score > 0.5
    return BaselineScore(esg_label, esg_score, tone_label, tone_score, risk, is_vague and is_hyped)


@lru_cache(maxsize=1)
def _pipelines():
    from transformers import pipeline
    esg = pipeline("text-classification", model=config.ESG_MODEL, truncation=True, max_length=512)
    tone = pipeline("text-classification", model=config.TONE_MODEL, truncation=True, max_length=512)
    return esg, tone


def score_texts(texts: Sequence[str], batch_size: int = 16) -> list[BaselineScore]:
    if not texts:
        return []
    esg, tone = _pipelines()
    esg_out = esg(list(texts), batch_size=batch_size)
    tone_out = tone(list(texts), batch_size=batch_size)
    return [
        score(e["label"], float(e["score"]), t["label"], float(t["score"]))
        for e, t in zip(esg_out, tone_out)
    ]
