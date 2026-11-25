"""Pick the claims to hand-label and pool candidate evidence for each.

Sampling (200 claims by default, seeded): every claim from the smaller reports, and an
even spread across the specificity range from the larger ones, so all three verdicts and
all five companies are represented.

Pooling: the passages shown for a claim are the union of the top EVIDENCE_K from BM25,
vector search, hybrid (fused, before reranking) and hybrid + reranker, plus the claim's own
chunk with the claim cut out. They are shuffled, so the labeller cannot tell which system
found which passage. Every system's ranking is saved, unseen by the labeller, for scoring.

    python -m scripts.export_gold_items            # writes eval/gold/items.jsonl
"""

from __future__ import annotations

import argparse
import logging
import random
from collections import defaultdict

from esg import config, db
from esg.embedding import embed_queries
from esg.eval import gold
from esg.retrieval.search import ClaimQuery, Retriever
from esg.verdict.verify import build_index

log = logging.getLogger("export-gold")


def sample(claims: list[dict], n: int, seed: int) -> list[dict]:
    by_report = defaultdict(list)
    for c in claims:
        by_report[c["report_id"]].append(c)
    # Smallest reports first: take all of a report while it fits its fair share.
    reports = sorted(by_report.values(), key=len)
    picked, remaining = [], n
    for i, rows in enumerate(reports):
        share = remaining // (len(reports) - i)
        if len(rows) <= share:
            picked += rows
        else:
            rows = sorted(rows, key=lambda c: c["specificity_score"])
            step = len(rows) / share
            picked += [rows[int(j * step)] for j in range(share)]  # even spread over specificity
        remaining = n - len(picked)
    random.Random(seed).shuffle(picked)
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    k = config.EVIDENCE_K

    conn = db.connect()
    claims = conn.execute(
        """SELECT c.report_id, c.chunk_id, c.sentence, c.char_start, c.char_end, c.claim_score,
                  c.specificity_score, r.company, r.fiscal_year, ch.seq, ch.section, ch.principle,
                  ch.page_start, ch.text AS chunk_text
           FROM claims c JOIN reports r ON r.id = c.report_id JOIN chunks ch ON ch.id = c.chunk_id
           ORDER BY c.report_id, ch.seq, c.char_start""").fetchall()
    chosen = sample(claims, args.n, args.seed)
    log.info("Sampled %d of %d claims", len(chosen), len(claims))

    retriever = Retriever()
    items = []
    for report_id in sorted({c["report_id"] for c in chosen}):
        rows = [c for c in chosen if c["report_id"] == report_id]
        index = build_index(db.report_passages(conn, report_id))
        queries = [ClaimQuery(c["chunk_id"], c["sentence"], c["char_start"], c["char_end"]) for c in rows]
        qvecs = embed_queries([q.text for q in queries])
        reranked = retriever.retrieve(index, queries, qvecs)
        for c, q, qv, top in zip(rows, queries, qvecs, reranked):
            systems = {
                "bm25": [index.passages[i].seq for i in index.bm25_ranking(q, k)],
                "vector": [index.passages[i].seq for i in index.vector_ranking(q, qv, k)],
                "hybrid": [h.passage.seq for h in index.hybrid(q, qv, k)],
                "hybrid_rerank": [h.passage.seq for h in top],
            }
            context = index.context(q)
            pool = {s for ranking in systems.values() for s in ranking} - {c["seq"]}
            passages = [index.passages[[p.seq for p in index.passages].index(s)] for s in sorted(pool)]
            shown = [{"chunk_seq": p.seq, "kind": p.kind, "label": p.label, "text": p.text, "is_context": False}
                     for p in passages]
            if context:
                shown.append({"chunk_seq": c["seq"], "kind": context.passage.kind,
                              "label": "rest of the claim's own passage", "text": context.text,
                              "is_context": True})
            key = gold.item_key(c["company"], c["fiscal_year"], c["seq"], c["char_start"])
            random.Random(key).shuffle(shown)
            for i, p in enumerate(shown, 1):
                p["pid"] = f"E{i}"
            items.append({
                "key": key, "company": c["company"], "fiscal_year": c["fiscal_year"],
                "chunk_seq": c["seq"], "char_start": c["char_start"], "char_end": c["char_end"],
                "section": c["section"], "principle": c["principle"], "page": c["page_start"],
                "sentence": c["sentence"], "chunk_text": c["chunk_text"],
                "claim_score": round(c["claim_score"], 4), "specificity_score": round(c["specificity_score"], 4),
                "passages": shown, "systems": systems,
            })
        log.info("Report %s: %d items", report_id, len(rows))

    order = {c["sentence"] + str(c["char_start"]): i for i, c in enumerate(chosen)}
    items.sort(key=lambda it: order[it["sentence"] + str(it["char_start"])])  # keep the shuffled order
    gold.write_jsonl(gold.ITEMS, items)
    sizes = [len(it["passages"]) for it in items]
    log.info("Wrote %d items to %s; %.1f passages per claim on average", len(items), gold.ITEMS,
             sum(sizes) / len(sizes))


if __name__ == "__main__":
    main()
