"""Okapi BM25 over one report's chunks. A report has a few hundred chunks, so in memory is fine.

The tokenizer keeps numbers and units ("14%", "2030", "kl") because figures are what
separate evidence from restatement, and drops common English stopwords.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

import numpy as np

_TOKEN = re.compile(r"[a-z]+|\d+(?:[.,]\d+)*%?")
_STOPWORDS = frozenset("""
a an and are as at be been being but by can could did do does for from had has have having he her
his i if in into is it its itself may more most must no not of on or our ours over shall she should
so such than that the their them then there these they this those through to under until up upon
us was we were what when where which while who whom why will with would you your also all any each
other per its i.e e.g etc
""".split())


def tokenize(text: str) -> list[str]:
    # Single letters are leftovers of abbreviations ("i.e." -> i, e), not words.
    return [t for t in _TOKEN.findall(text.lower())
            if t not in _STOPWORDS and not (len(t) == 1 and t.isalpha())]


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in docs]
        self.lengths = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.avg_length = float(self.lengths.mean()) if len(self.docs) else 0.0
        df = Counter(term for d in self.docs for term in d)
        n = len(self.docs)
        # The "+1" form of IDF never goes negative, so very common terms still count a little.
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(len(self.docs))
        if not self.docs:
            return out
        norm = self.k1 * (1 - self.b + self.b * self.lengths / (self.avg_length or 1))
        for term in set(tokenize(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            tf = np.array([d.get(term, 0) for d in self.docs], dtype=float)
            out += idf * tf * (self.k1 + 1) / (tf + norm)
        return out
