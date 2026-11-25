"""Evidence retrieval for a claim, within the claim's own report.

    BM25 top-N  ┐
                ├─ reciprocal rank fusion ─> top RETRIEVAL_DEPTH ─> cross-encoder rerank ─> top k
    vector top-N┘                               (+ the claim's own chunk, minus the claim)

The claim's own chunk is left out of BM25 and vector search: it contains the claim, so it
would always win. What else that chunk says can still be evidence, so the rest of it (with
the claim sentence cut out) is added to the reranker's candidates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np

from .. import config
from .bm25 import BM25

RRF_K = 60  # the usual constant from Cormack et al. (2009)
MIN_CONTEXT_WORDS = 12


@dataclass(frozen=True)
class Passage:
    chunk_id: int
    seq: int
    kind: str           # text | table
    section: str | None
    principle: int | None
    page_start: int
    text: str

    @property
    def label(self) -> str:
        where = f"Principle {self.principle}" if self.principle else f"Section {self.section or '-'}"
        return f"{self.kind}, {where}, p. {self.page_start}"


@dataclass(frozen=True)
class ClaimQuery:
    chunk_id: int     # the chunk the claim came from
    text: str         # the claim sentence
    start: int        # its offsets in that chunk
    end: int


@dataclass
class Hit:
    passage: Passage
    text: str                     # what the reranker and NLI see (own chunk: claim cut out)
    rrf: float | None = None      # None for the own-chunk context
    rerank: float | None = None
    is_context: bool = False


@dataclass
class ReportIndex:
    passages: list[Passage]
    embeddings: np.ndarray        # (n, dim), L2-normalised
    _pos: dict[int, int] = field(init=False, repr=False)

    def __post_init__(self):
        self._pos = {p.chunk_id: i for i, p in enumerate(self.passages)}

    @cached_property
    def bm25(self) -> BM25:
        return BM25([p.text for p in self.passages])

    def _rank(self, scores: np.ndarray, exclude: int | None, depth: int) -> list[int]:
        scores = scores.astype(float).copy()
        if exclude is not None and exclude in self._pos:
            scores[self._pos[exclude]] = -np.inf
        order = np.argsort(-scores, kind="stable")
        return [int(i) for i in order[:depth] if np.isfinite(scores[i])]

    def bm25_ranking(self, claim: ClaimQuery, depth: int) -> list[int]:
        return self._rank(self.bm25.scores(claim.text), claim.chunk_id, depth)

    def vector_ranking(self, claim: ClaimQuery, query_vec: np.ndarray, depth: int) -> list[int]:
        return self._rank(self.embeddings @ query_vec, claim.chunk_id, depth)

    def hybrid(self, claim: ClaimQuery, query_vec: np.ndarray, depth: int) -> list[Hit]:
        fused: dict[int, float] = {}
        for ranking in (self.bm25_ranking(claim, 3 * depth), self.vector_ranking(claim, query_vec, 3 * depth)):
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        top = sorted(fused, key=lambda i: -fused[i])[:depth]
        return [Hit(self.passages[i], self.passages[i].text, rrf=fused[i]) for i in top]

    def context(self, claim: ClaimQuery) -> Hit | None:
        """The claim's own chunk with the claim cut out, if enough is left to be evidence."""
        pos = self._pos.get(claim.chunk_id)
        if pos is None:
            return None
        p = self.passages[pos]
        rest = (p.text[:claim.start] + " " + p.text[claim.end:]).strip()
        if len(rest.split()) < MIN_CONTEXT_WORDS:
            return None
        return Hit(p, rest, is_context=True)


class Reranker:
    def __init__(self, model_name: str = config.RERANK_MODEL):
        from sentence_transformers import CrossEncoder
        self.name = model_name
        self.model = CrossEncoder(model_name, max_length=512, device="cpu")

    def score(self, pairs: Sequence[tuple[str, str]]) -> np.ndarray:
        if not pairs:
            return np.zeros(0)
        return np.asarray(self.model.predict(list(pairs), batch_size=16, show_progress_bar=False),
                          dtype=float)


class Retriever:
    """Hybrid retrieval plus reranking for many claims of one report at once."""

    def __init__(self, reranker: Reranker | None = None, depth: int = config.RETRIEVAL_DEPTH,
                 k: int = config.EVIDENCE_K):
        self.reranker = reranker or Reranker()
        self.depth, self.k = depth, k

    def candidates(self, index: ReportIndex, claims: Sequence[ClaimQuery],
                   query_vecs: np.ndarray) -> list[list[Hit]]:
        out = []
        for claim, qv in zip(claims, query_vecs):
            hits = index.hybrid(claim, qv, self.depth)
            ctx = index.context(claim)
            out.append(hits + ([ctx] if ctx else []))
        return out

    def retrieve(self, index: ReportIndex, claims: Sequence[ClaimQuery],
                 query_vecs: np.ndarray) -> list[list[Hit]]:
        """Top-k reranked evidence per claim."""
        pools = self.candidates(index, claims, query_vecs)
        pairs = [(c.text, h.text) for c, pool in zip(claims, pools) for h in pool]
        scores = iter(self.reranker.score(pairs))
        result = []
        for pool in pools:
            for h in pool:
                h.rerank = float(next(scores))
            result.append(sorted(pool, key=lambda h: -h.rerank)[:self.k])
        return result
