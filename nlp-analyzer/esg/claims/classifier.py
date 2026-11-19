"""A fine-tuned binary text classifier saved by scripts/train_classifier.py.

Used by the evaluation harness and the analyzer worker, so both score text the same way.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np


class TextClassifier:
    def __init__(self, model_dir: str | Path, max_length: int | None = None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.model_dir = Path(model_dir)
        meta_path = self.model_dir / "train_meta.json"
        self.meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        self.max_length = max_length or self.meta.get("max_length", 256)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_dir).eval()
        self._torch = torch

    @property
    def name(self) -> str:
        return self.meta.get("name", self.model_dir.name)

    def predict_proba(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        """P(label = 1) for each text."""
        torch = self._torch
        out = []
        # Sorting by length keeps padding (and so CPU time) down.
        order = np.argsort([len(t) for t in texts])
        with torch.inference_mode():
            for i in range(0, len(texts), batch_size):
                batch = [texts[j] for j in order[i:i + batch_size]]
                enc = self.tokenizer(batch, truncation=True, max_length=self.max_length,
                                     padding=True, return_tensors="pt")
                logits = self.model(**enc).logits
                out.append(torch.softmax(logits, dim=-1)[:, 1].numpy())
        probs = np.empty(len(texts), dtype=np.float32)
        if out:
            probs[order] = np.concatenate(out)
        return probs


def model_exists(model_dir: str | Path) -> bool:
    return (Path(model_dir) / "config.json").exists()
