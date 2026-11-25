"""Sentence embeddings for chunks. The model loads on first use (it is a few hundred MB)."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

import numpy as np

from . import config


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(config.EMBED_MODEL, device="cpu")


def embed_passages(texts: Sequence[str]) -> np.ndarray:
    """Return one L2-normalised vector per text, shape (len(texts), EMBED_DIM)."""
    if not texts:
        return np.zeros((0, config.EMBED_DIM), dtype=np.float32)
    vectors = _model().encode(
        list(texts), batch_size=config.EMBED_BATCH, normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False,
    )
    if vectors.shape[1] != config.EMBED_DIM:
        raise ValueError(
            f"{config.EMBED_MODEL} gives {vectors.shape[1]}-d vectors; the schema expects {config.EMBED_DIM}"
        )
    return vectors.astype(np.float32)


# bge models expect this instruction on short queries (not on passages).
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def embed_queries(texts: Sequence[str]) -> np.ndarray:
    """Like embed_passages, for search queries (claims)."""
    return embed_passages([QUERY_INSTRUCTION + t for t in texts])
