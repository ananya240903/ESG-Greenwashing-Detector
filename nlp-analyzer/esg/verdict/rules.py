"""Turn specificity, NLI and reranker scores into a verdict with a cited reason.

Two orders of the same checks:

vague-first (order="vague_first"):
1. vague:         specificity < vague_below. Too general to check, whatever the evidence says.
2. unsupported:   a passage contradicts the claim (P(contradiction) >= contradict_at) more
                  strongly than any passage supports it.
3. substantiated: a passage backs the claim (see "support" below); cite it.
4. unsupported:   nothing among the retrieved passages backs it.

evidence-first (order="evidence_first"): the contradiction and support checks come first, and
only a claim nothing backs can be vague. This matches how people judged the gold set: a
generic sentence ("we have adopted cleaner technologies") next to a table of figures that
bears it out counts as substantiated.

Support: P(entailment) >= entail_at for some passage, or, when rerank_at is set, a
reranker relevance score >= rerank_at. NLI models are trained on prose and often miss
support in tables of figures; the reranker is a second, independent signal.

Kept separate from the model code so the rules can be unit-tested and the thresholds tuned
on the gold set without re-running any model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .. import config


@dataclass(frozen=True)
class Thresholds:
    vague_below: float = config.VAGUE_BELOW
    entail_at: float = config.ENTAIL_AT
    contradict_at: float = config.CONTRADICT_AT
    rerank_at: float | None = config.RERANK_AT       # None: the reranker does not count as support
    order: str = config.VERDICT_ORDER                 # vague_first | evidence_first


@dataclass(frozen=True)
class EvidenceScore:
    chunk_id: int
    label: str          # e.g. "table, Principle 6, p. 31"
    entailment: float
    contradiction: float
    rerank: float | None = None   # cross-encoder relevance (logit), if the passage was reranked


@dataclass(frozen=True)
class Verdict:
    label: str          # substantiated | vague | unsupported
    confidence: float
    reason: str
    cited_chunk_ids: tuple[int, ...]


def _vague(specificity: float) -> Verdict:
    return Verdict("vague", 1 - specificity,
                   f"Too general to check: specificity {specificity:.2f} (no figures, targets "
                   f"or concrete actions), and no retrieved passage backs it.", ())


def _check_evidence(evidence: Sequence[EvidenceScore], th: Thresholds) -> Verdict | None:
    """Substantiated or contradicted, or None when the evidence settles nothing."""
    best = max(evidence, key=lambda e: e.entailment, default=None)
    worst = max(evidence, key=lambda e: e.contradiction, default=None)
    if worst and worst.contradiction >= th.contradict_at and worst.contradiction > (best.entailment if best else 0):
        return Verdict("unsupported", worst.contradiction,
                       f"Contradicted by {worst.label} (contradiction {worst.contradiction:.2f}).",
                       (worst.chunk_id,))
    if best and best.entailment >= th.entail_at:
        return Verdict("substantiated", best.entailment,
                       f"Backed by {best.label} (entailment {best.entailment:.2f}).", (best.chunk_id,))
    if th.rerank_at is not None:
        ranked = [e for e in evidence if e.rerank is not None]
        top = max(ranked, key=lambda e: e.rerank, default=None)
        if top and top.rerank >= th.rerank_at:
            return Verdict("substantiated", best.entailment if best else 0.0,
                           f"Backed by {top.label} (reranker relevance {top.rerank:.1f}).", (top.chunk_id,))
    return None


def decide(specificity: float, evidence: Sequence[EvidenceScore], th: Thresholds = Thresholds()) -> Verdict:
    if th.order == "vague_first" and specificity < th.vague_below:
        return _vague(specificity)
    settled = _check_evidence(evidence, th)
    if settled:
        return settled
    if specificity < th.vague_below:
        return _vague(specificity)
    best = max(evidence, key=lambda e: e.entailment, default=None)
    top = f" (best entailment {best.entailment:.2f}, {best.label})" if best else ""
    return Verdict("unsupported", 1 - (best.entailment if best else 0),
                   f"No retrieved passage backs it{top}.", ())
