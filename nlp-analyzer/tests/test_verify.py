"""Verifier.check: which claims get the expensive evidence check, under each rule order."""

import numpy as np

from esg.retrieval.search import ClaimQuery, Hit, Passage, ReportIndex
from esg.verdict import verify
from esg.verdict.rules import Thresholds

P = [Passage(i, i, "text", "C", 6, i, f"passage {i} about water use") for i in range(1, 4)]
INDEX = ReportIndex(P, np.eye(3, dtype=np.float32))
CLAIMS = [ClaimQuery(1, "We care deeply about the planet and water.", 0, 10),
          ClaimQuery(2, "We cut water use by 14% in FY24 across plants.", 0, 10)]


class StubRetriever:
    k = 2

    class reranker:
        name = "stub-rerank"

    def retrieve(self, index, claims, qvecs):
        return [[Hit(P[2], P[2].text, rrf=0.1, rerank=5.0)] for _ in claims]


class StubNLI:
    name = "stub-nli"

    def scores(self, pairs):
        return np.array([[0.9, 0.0]] * len(pairs), dtype=np.float32)  # everything entailed


def run(order, monkeypatch):
    monkeypatch.setattr(verify, "embed_queries", lambda texts: np.ones((len(texts), 3), dtype=np.float32))
    v = verify.Verifier(StubRetriever(), StubNLI(), Thresholds(0.5, 0.5, 0.8, rerank_at=None, order=order))
    return [c.verdict.label for c in v.check(CLAIMS, [0.1, 0.9], INDEX)]


def test_vague_first_skips_the_evidence_check_for_generic_claims(monkeypatch):
    assert run("vague_first", monkeypatch) == ["vague", "substantiated"]


def test_evidence_first_checks_every_claim(monkeypatch):
    # The generic claim is backed by a passage, so under evidence-first it is substantiated.
    assert run("evidence_first", monkeypatch) == ["substantiated", "substantiated"]
