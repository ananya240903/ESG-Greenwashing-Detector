"""Claims -> evidence -> verdicts for one report.

Used by the analyzer worker and by the gold-set evaluation, so both run the same code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..embedding import embed_queries
from ..retrieval.search import ClaimQuery, Hit, Passage, ReportIndex, Retriever
from .nli import NLI
from .rules import EvidenceScore, Thresholds, Verdict, decide


@dataclass
class Checked:
    evidence: list[Hit]
    scores: list[EvidenceScore]
    verdict: Verdict


def build_index(rows: Sequence[dict]) -> ReportIndex:
    """rows: chunks with id, seq, kind, section, principle, page_start, text, embedding."""
    passages = [Passage(r["id"], r["seq"], r["kind"], r["section"], r["principle"], r["page_start"], r["text"])
                for r in rows]
    def vec(v):  # pgvector returns its own Vector type
        return np.asarray(v.to_numpy() if hasattr(v, "to_numpy") else v, dtype=np.float32)

    emb = np.stack([vec(r["embedding"]) for r in rows]) if rows else np.zeros((0, 384), dtype=np.float32)
    return ReportIndex(passages, emb)


class Verifier:
    def __init__(self, retriever: Retriever | None = None, nli: NLI | None = None,
                 thresholds: Thresholds | None = None):
        self.retriever = retriever or Retriever()
        self.nli = nli or NLI()
        self.thresholds = thresholds or Thresholds()

    @property
    def model_name(self) -> str:
        t = self.thresholds
        return (f"{self.retriever.reranker.name}+{self.nli.name}"
                f"@v{t.vague_below:g}/e{t.entail_at:g}/c{t.contradict_at:g}")

    def score_evidence(self, claims: Sequence[ClaimQuery], index: ReportIndex) -> list[list[tuple[Hit, EvidenceScore]]]:
        """Retrieve and NLI-score evidence; no thresholds involved, so results can be re-decided."""
        if not claims:
            return []
        evidence = self.retriever.retrieve(index, claims, embed_queries([c.text for c in claims]))
        pairs = [(h.text, c.text) for c, hits in zip(claims, evidence) for h in hits]
        nli = iter(self.nli.scores(pairs))
        out = []
        for hits in evidence:
            row = []
            for h in hits:
                ent, con = next(nli)
                row.append((h, EvidenceScore(h.passage.chunk_id, h.passage.label, float(ent), float(con), h.rerank)))
            out.append(row)
        return out

    def check(self, claims: Sequence[ClaimQuery], specificity: Sequence[float], index: ReportIndex) -> list[Checked]:
        """Verdicts for a report's claims.

        Under the vague-first rule, a claim below the vagueness threshold is vague whatever
        the evidence says, so it skips the reranker and NLI (most of the CPU time); its
        evidence is the hybrid search's top k, kept for display. Under evidence-first, every
        claim's evidence is checked, because support can make a generic claim substantiated.
        """
        skip = self.thresholds.order == "vague_first"
        vague = [skip and s < self.thresholds.vague_below for s in specificity]
        to_check = [c for c, v in zip(claims, vague) if not v]
        scored = iter(self.score_evidence(to_check, index))
        out = []
        qvecs = embed_queries([c.text for c, v in zip(claims, vague) if v]) if any(vague) else []
        qvecs = iter(qvecs)
        for claim, spec, is_vague in zip(claims, specificity, vague):
            if is_vague:
                hits = index.hybrid(claim, next(qvecs), self.retriever.k)
                out.append(Checked(hits, [], decide(spec, [], self.thresholds)))
            else:
                row = next(scored)
                out.append(Checked([h for h, _ in row], [s for _, s in row],
                                   decide(spec, [s for _, s in row], self.thresholds)))
        return out
