"""Binary classification metrics, with bootstrap confidence intervals for F1."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (accuracy_score, f1_score, precision_score, recall_score,
                             roc_auc_score)


def binary_metrics(y_true, y_pred, y_score=None) -> dict:
    """Metrics for the positive class (label 1), plus macro F1 and, given scores, ROC AUC."""
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    m = {
        "n": int(len(y_true)),
        "positives": int(y_true.sum()),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
    }
    if y_score is not None and len(set(y_true)) == 2:
        m["roc_auc"] = float(roc_auc_score(y_true, np.asarray(y_score, dtype=float)))
    return m


def bootstrap_f1_ci(y_true, y_pred, n_resamples: int = 1000, seed: int = 0,
                    alpha: float = 0.05) -> tuple[float, float]:
    """95% percentile bootstrap interval for positive-class F1."""
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    rng = np.random.default_rng(seed)
    n = len(y_true)
    scores = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.integers(0, n, n)
        scores[i] = f1_score(y_true[idx], y_pred[idx], zero_division=0)
    lo, hi = np.quantile(scores, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)
