"""ClaimExtractor wiring, with stub classifiers so no model is needed."""

import numpy as np

from esg.claims.extract import ClaimExtractor, prominence


class Stub:
    def __init__(self, name, fn):
        self.name, self.fn, self.seen = name, fn, []

    def predict_proba(self, texts):
        self.seen.extend(texts)
        return np.array([self.fn(t) for t in texts], dtype=np.float32)


def make_extractor(threshold=0.5):
    ex = ClaimExtractor.__new__(ClaimExtractor)
    ex.claims = Stub("claims-m", lambda t: 0.9 if "emission" in t or "water" in t else 0.1)
    ex.specificity = Stub("spec-m", lambda t: 0.8 if "%" in t else 0.2)
    ex.threshold = threshold
    return ex


CHUNKS = [
    {"id": 7, "section": "B", "text": "We are committed to a greener planet and lower emissions.\n"
                                      "Our board met eleven times during the financial year."},
    {"id": 9, "section": "C", "text": "EI-3. Water withdrawal by source, in the format below:\n"
                                      "We cut water use per tonne of product by 14% in FY24."},
]


def test_keeps_claims_above_threshold_with_offsets_and_scores():
    ex = make_extractor()
    claims = ex.extract(CHUNKS)
    assert [(c.chunk_id, c.sentence.text) for c in claims] == [
        (7, "We are committed to a greener planet and lower emissions."),
        (9, "We cut water use per tonne of product by 14% in FY24."),
    ]
    for c in claims:
        text = next(ch["text"] for ch in CHUNKS if ch["id"] == c.chunk_id)
        assert text[c.sentence.start:c.sentence.end] == c.sentence.text
    assert [round(c.specificity_score, 1) for c in claims] == [0.2, 0.8]
    assert [c.prominence for c in claims] == [1.5, 1.0]


def test_specificity_runs_only_on_kept_claims():
    ex = make_extractor()
    ex.extract(CHUNKS)
    assert len(ex.claims.seen) == 3  # the BRSR question line is never a candidate
    assert len(ex.specificity.seen) == 2


def test_no_claims_means_no_specificity_call():
    ex = make_extractor(threshold=0.95)
    assert ex.extract(CHUNKS) == []
    assert ex.specificity.seen == []
    assert ex.model_name == "claims-m+spec-m@0.95"


def test_prominence_weights_section_b():
    assert prominence("B") == 1.5
    assert prominence("C") == prominence(None) == 1.0
