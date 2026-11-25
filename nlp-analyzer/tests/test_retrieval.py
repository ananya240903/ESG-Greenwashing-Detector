import numpy as np
import pytest

from esg.retrieval.bm25 import BM25, tokenize
from esg.retrieval.search import ClaimQuery, Passage, ReportIndex, Retriever


def test_tokenize_keeps_figures_and_drops_stopwords():
    assert tokenize("We cut water use by 14% in FY 2023-24, i.e. 1,234.5 kL.") == \
        ["cut", "water", "use", "14%", "fy", "2023", "24", "1,234.5", "kl"]


def test_bm25_prefers_rare_matching_terms():
    bm = BM25(["water withdrawal by source in kilolitres",
               "the company and the board and the company",
               "scope 1 emissions tonnes co2"])
    s = bm.scores("water withdrawal")
    assert s.argmax() == 0 and s[1] == 0
    assert bm.scores("unknownword").sum() == 0


CLAIM_TEXT = "We reduced our water withdrawal sharply this year."
OWN = ("The board approved the policy in May. " + CLAIM_TEXT +
       " Withdrawal fell from 12.1 to 9.8 million kL across all manufacturing plants in India.")
PASSAGES = [
    Passage(1, 0, "text", "C", 6, 10, OWN),
    Passage(2, 1, "table", "C", 6, 11, "Water withdrawal by source (kL): surface 9.8 million, groundwater 0.2"),
    Passage(3, 2, "text", "C", 3, 15, "Employee wellbeing programmes cover all permanent staff"),
    Passage(4, 3, "text", "A", None, 2, "Registered office address and contact details of the company"),
]
# Toy unit vectors: chunk 3 is closest to the query vector, chunk 2 second.
EMB = np.array([[1, 0, 0], [0.6, 0.8, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
EMB /= np.linalg.norm(EMB, axis=1, keepdims=True)
QV = np.array([0, 1, 0], dtype=np.float32)


@pytest.fixture
def claim():
    start = OWN.index(CLAIM_TEXT)
    return ClaimQuery(chunk_id=1, text=CLAIM_TEXT, start=start, end=start + len(CLAIM_TEXT))


def test_own_chunk_is_excluded_from_search(claim):
    index = ReportIndex(PASSAGES, EMB)
    assert 0 not in index.bm25_ranking(claim, 10)
    assert 0 not in index.vector_ranking(claim, QV, 10)
    assert index.bm25_ranking(claim, 10)[0] == 1     # the water table
    assert index.vector_ranking(claim, QV, 10)[0] == 2


def test_hybrid_fuses_both_rankings(claim):
    hits = ReportIndex(PASSAGES, EMB).hybrid(claim, QV, depth=2)
    # Chunk 2 is 1st in BM25 and 2nd in vector search, so it beats chunk 3 (1st in vector only).
    assert [h.passage.chunk_id for h in hits] == [2, 3]


def test_context_is_own_chunk_without_the_claim(claim):
    ctx = ReportIndex(PASSAGES, EMB).context(claim)
    assert ctx.is_context and ctx.passage.chunk_id == 1
    assert CLAIM_TEXT not in ctx.text and "9.8 million kL" in ctx.text


class StubReranker:
    name = "stub"

    def score(self, pairs):
        # Prefer passages mentioning a figure in kL.
        return np.array([2.0 if "kL" in p else 0.0 for _, p in pairs])


def test_retrieve_reranks_candidates_and_context(claim):
    retriever = Retriever(reranker=StubReranker(), depth=3, k=2)
    (hits,) = retriever.retrieve(ReportIndex(PASSAGES, EMB), [claim], QV[None, :])
    assert len(hits) == 2
    assert {h.passage.chunk_id for h in hits} == {1, 2}   # context and the table, both mention kL
    assert all(h.rerank == 2.0 for h in hits)


def test_nli_windows_cover_long_passages_with_overlap():
    from esg.verdict.nli import windows
    short = "Scope 1 emissions fell 12% in FY24."
    assert windows(short) == [short]
    words = [f"w{i}" for i in range(250)]
    w = windows(" ".join(words), size=110, stride=80)
    assert w[0].split()[0] == "w0" and w[-1].split()[-1] == "w249"
    assert all(len(x.split()) <= 110 for x in w)
    assert "w100" in w[0] and "w100" in w[1]  # windows overlap
