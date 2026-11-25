"""Worker 2: report.parsed -> analyse the report.

1. Baseline: the original FinBERT heuristic on every text chunk (kept as the baseline to beat).
2. Claims: environmental claim sentences, with specificity and prominence (Phase 2).
3. Verification: evidence for each claim from the same report, and a verdict (Phase 3).

Run: python -m esg.workers.analyzer_worker
"""

from __future__ import annotations

import logging
import time
from collections import Counter

import psycopg

from .. import baseline, config, db, kafka_io
from ..claims.extract import ClaimExtractor, load_extractor
from ..retrieval.search import ClaimQuery
from ..verdict.verify import Verifier, build_index

log = logging.getLogger("analyzer-worker")


def claim_records(conn, report_id: int, chunks: list[dict], extractor: ClaimExtractor,
                  verifier: Verifier) -> list[dict]:
    claims = extractor.extract(chunks)
    queries = [ClaimQuery(c.chunk_id, c.sentence.text, c.sentence.start, c.sentence.end) for c in claims]
    checked = verifier.check(queries, [c.specificity_score for c in claims],
                             build_index(db.report_passages(conn, report_id)))
    records = []
    for c, ch in zip(claims, checked):
        v = ch.verdict
        records.append({
            "chunk_id": c.chunk_id, "sentence": c.sentence.text,
            "char_start": c.sentence.start, "char_end": c.sentence.end,
            "claim_score": c.claim_score, "specificity_score": c.specificity_score,
            "prominence": c.prominence, "topics": list(c.topics), "model": extractor.model_name,
            "evidence": [(h.passage.chunk_id, rank, h.rrf, h.rerank) for rank, h in enumerate(ch.evidence, 1)],
            "verdict": (v.label, v.confidence, v.reason, v.cited_chunk_ids, verifier.model_name),
        })
    return records


def analyse(conn: psycopg.Connection, report_id: int, extractor: ClaimExtractor | None,
            verifier: Verifier | None) -> None:
    if db.get_report(conn, report_id) is None:
        log.warning("Report %s not found; skipping", report_id)
        return
    db.set_status(conn, report_id, "ANALYZING")
    started = time.monotonic()
    try:
        chunks = db.text_chunks(conn, report_id)
        scores = baseline.score_texts([c["text"] for c in chunks])
        baseline_rows = [
            (c["id"], s.esg_label, s.esg_score, s.tone_label, s.tone_score, s.risk_score, s.flagged)
            for c, s in zip(chunks, scores)
        ]
        claims = None
        if extractor is not None and verifier is not None:
            claims = claim_records(conn, report_id, chunks, extractor, verifier)
        db.save_analysis(conn, report_id, baseline_rows, claims)
    except Exception as exc:
        if db.is_connection_lost(conn):
            raise  # let db.Session reconnect and retry the job
        log.exception("Analysing report %s failed", report_id)
        db.set_status(conn, report_id, "FAILED", f"analyze: {exc}")
        return
    verdicts = Counter(c["verdict"][0] for c in claims or [])
    log.info("Report %s: %d chunks scored (%d flagged by baseline); %s claims %s in %.1fs",
             report_id, len(baseline_rows), sum(r[-1] for r in baseline_rows),
             "no" if claims is None else len(claims), dict(verdicts), time.monotonic() - started)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    extractor = load_extractor()
    verifier = Verifier() if extractor is not None else None
    session = db.Session()
    kafka_io.run_consumer(config.TOPIC_REPORT_PARSED, "analyzer-workers",
                          lambda report_id: session.run(analyse, report_id, extractor, verifier))


if __name__ == "__main__":
    main()
