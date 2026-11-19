"""The systems the harness compares, each turned into predictions for one task.

The FinBERT baseline was not built for these tasks, so it is mapped onto them as
directly as its outputs allow:
- claims:      predict "environmental claim" when FinBERT-ESG's top label is Environmental.
- specificity: the old tool's flag ("vague and hyped") means not specific. A second,
               more generous reading counts any passage the ESG model is unsure about
               (label None or confidence < 0.7) as vague, regardless of tone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .. import baseline, config
from ..claims.classifier import TextClassifier, model_exists


@dataclass
class Predictions:
    system: str
    description: str
    pred: np.ndarray          # 0/1
    score: np.ndarray | None  # higher = more likely label 1; None if the system has no score


def _finbert_outputs(texts: Sequence[str]):
    esg, tone = baseline._pipelines()
    esg_all = esg(list(texts), top_k=None, batch_size=16)  # every label's probability
    tone_top = tone(list(texts), batch_size=16)
    return esg_all, tone_top


def finbert(task: str, texts: Sequence[str]) -> list[Predictions]:
    esg_all, tone_top = _finbert_outputs(texts)
    p_env = np.array([next(d["score"] for d in row if d["label"] == "Environmental") for row in esg_all])
    top = [max(row, key=lambda d: d["score"]) for row in esg_all]
    if task == "claims":
        pred = np.array([t["label"] == "Environmental" for t in top], dtype=int)
        return [Predictions("finbert-esg", "FinBERT-ESG top label is Environmental", pred, p_env)]

    scored = [baseline.score(t["label"], float(t["score"]), tn["label"], float(tn["score"]))
              for t, tn in zip(top, tone_top)]
    risk = np.array([s.risk_score for s in scored])
    flagged = np.array([s.flagged for s in scored], dtype=int)
    vague = np.array([s.esg_label == "None" or s.esg_score < 0.7 for s in scored], dtype=int)
    return [
        Predictions("finbert-flag", "Old tool's flag (vague and hyped) = not specific",
                    1 - flagged, 100 - risk),
        Predictions("finbert-vague", "FinBERT-ESG unsure (None or < 0.7) = not specific",
                    1 - vague, np.array([s.esg_score for s in scored])),
    ]


def fine_tuned(task: str, texts: Sequence[str]) -> Predictions | None:
    model_dir = config.CLAIM_MODEL_DIR if task == "claims" else config.SPECIFICITY_MODEL_DIR
    if not model_exists(model_dir):
        return None
    clf = TextClassifier(model_dir)
    probs = clf.predict_proba(list(texts))
    return Predictions(clf.name, f"Fine-tuned {clf.meta.get('base_model', '')}",
                       (probs >= 0.5).astype(int), probs)


def all_systems(task: str, texts: Sequence[str]) -> list[Predictions]:
    systems = finbert(task, texts)
    tuned = fine_tuned(task, texts)
    return systems + ([tuned] if tuned else [])
