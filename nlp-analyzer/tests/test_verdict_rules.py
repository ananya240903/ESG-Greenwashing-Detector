from esg.verdict.rules import EvidenceScore, Thresholds, decide

TH = Thresholds(vague_below=0.5, entail_at=0.5, contradict_at=0.8, rerank_at=None, order="vague_first", use_numbers=False)


def ev(cid, ent, con=0.0):
    return EvidenceScore(cid, f"table, Principle 6, p. {cid}", ent, con)


def test_low_specificity_is_vague_even_with_support():
    v = decide(0.2, [ev(1, 0.95)], TH)
    assert v.label == "vague" and v.cited_chunk_ids == ()
    assert v.confidence == 0.8


def test_best_entailing_passage_is_cited():
    v = decide(0.9, [ev(1, 0.3), ev(2, 0.85), ev(3, 0.6)], TH)
    assert v.label == "substantiated"
    assert v.cited_chunk_ids == (2,)
    assert "p. 2" in v.reason and "0.85" in v.reason


def test_strong_contradiction_beats_weaker_support():
    v = decide(0.9, [ev(1, 0.6), ev(2, 0.1, con=0.9)], TH)
    assert v.label == "unsupported" and v.cited_chunk_ids == (2,)
    assert "Contradicted" in v.reason


def test_support_wins_over_a_weaker_contradiction():
    assert decide(0.9, [ev(1, 0.95), ev(2, 0.0, con=0.85)], TH).label == "substantiated"


def test_specific_claim_with_no_backing_is_unsupported():
    v = decide(0.9, [ev(1, 0.2), ev(2, 0.4)], TH)
    assert v.label == "unsupported" and v.cited_chunk_ids == ()
    assert "best entailment 0.40" in v.reason


def test_no_evidence_at_all_is_unsupported():
    assert decide(0.9, [], TH).label == "unsupported"


EF = Thresholds(vague_below=0.5, entail_at=0.5, contradict_at=0.8, rerank_at=None, order="evidence_first", use_numbers=False)


def test_evidence_first_lets_a_generic_claim_be_substantiated():
    v = decide(0.1, [ev(4, 0.9)], EF)
    assert v.label == "substantiated" and v.cited_chunk_ids == (4,)


def test_evidence_first_still_calls_unbacked_generic_claims_vague():
    v = decide(0.1, [ev(4, 0.2)], EF)
    assert v.label == "vague" and "no retrieved passage backs it" in v.reason


def test_reranker_counts_as_support_only_when_enabled():
    from esg.verdict.rules import EvidenceScore
    e = [EvidenceScore(9, "table, Principle 6, p. 9", 0.1, 0.0, rerank=7.5)]
    assert decide(0.9, e, EF).label == "unsupported"
    with_rerank = Thresholds(0.5, 0.5, 0.8, rerank_at=6.0, order="evidence_first", use_numbers=False)
    v = decide(0.9, e, with_rerank)
    assert v.label == "substantiated" and v.cited_chunk_ids == (9,) and "reranker relevance 7.5" in v.reason


def test_numbers_check_backs_or_rejects_a_claim_when_enabled():
    from esg.verdict.numbers import NumberCheck
    on = Thresholds(0.5, 0.5, 0.8, rerank_at=None, order="evidence_first", use_numbers=True)
    found = NumberCheck(("94%",), (31,), ("table, Principle 6, p. 31",))
    missing = NumberCheck(("2,928.07",), (None,), (None,))
    v = decide(0.2, [ev(1, 0.1)], on, found)
    assert v.label == "substantiated" and v.cited_chunk_ids == (31,) and "94%" in v.reason
    v = decide(0.2, [ev(1, 0.1)], on, missing)   # specific figures, found nowhere: not "vague"
    assert v.label == "unsupported" and "nowhere else" in v.reason
    assert decide(0.2, [ev(1, 0.1)], EF, found).label == "vague"   # ignored when switched off
