"""Natural language inference: does an evidence passage entail the claim?

Premise = evidence passage, hypothesis = claim sentence. NLI models are trained on short
premises (a sentence or two), and a 500-token table is far outside that, so each passage is
cut into overlapping windows of WINDOW_WORDS words; a passage's entailment and contradiction
scores are the highest over its windows.

Model choice: cross-encoder/nli-roberta-base. DeBERTa-v3 NLI models score higher on
benchmarks, but on this CPU they were 12x slower (2.6 s per window against 0.22 s).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .. import config

WINDOW_WORDS = 110
STRIDE_WORDS = 80


def windows(text: str, size: int = WINDOW_WORDS, stride: int = STRIDE_WORDS) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [text]
    starts = range(0, len(words) - size + stride, stride)
    return [" ".join(words[s:s + size]) for s in starts]


class NLI:
    def __init__(self, model_name: str = config.NLI_MODEL):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name).eval()
        labels = {v.lower(): k for k, v in self.model.config.id2label.items()}
        self.entail_idx, self.contra_idx = labels["entailment"], labels["contradiction"]
        self._torch = torch

    def _score_windows(self, pairs: Sequence[tuple[str, str]], batch_size: int) -> np.ndarray:
        torch = self._torch
        out = np.zeros((len(pairs), 2), dtype=np.float32)
        order = np.argsort([len(p) for p, _ in pairs])  # less padding per batch
        with torch.inference_mode():
            for i in range(0, len(pairs), batch_size):
                idx = order[i:i + batch_size]
                enc = self.tokenizer([pairs[j][0] for j in idx], [pairs[j][1] for j in idx],
                                     truncation="only_first", max_length=256, padding=True,
                                     return_tensors="pt")
                probs = torch.softmax(self.model(**enc).logits, dim=-1).numpy()
                out[idx, 0] = probs[:, self.entail_idx]
                out[idx, 1] = probs[:, self.contra_idx]
        return out

    def scores(self, pairs: Sequence[tuple[str, str]], batch_size: int = 16) -> np.ndarray:
        """(premise, hypothesis) pairs -> array (n, 2): P(entailment), P(contradiction),
        each the maximum over the premise's windows."""
        expanded, owner = [], []
        for i, (premise, hypothesis) in enumerate(pairs):
            for w in windows(premise):
                expanded.append((w, hypothesis))
                owner.append(i)
        out = np.zeros((len(pairs), 2), dtype=np.float32)
        if not expanded:
            return out
        scored = self._score_windows(expanded, batch_size)
        np.maximum.at(out, np.array(owner), scored)
        return out
