"""Worker 2: report.parsed -> analyse the report's text chunks.

1. Baseline: the original FinBERT heuristic on every text chunk (kept as the baseline to beat).
2. Claims: environmental claim sentences, with specificity and prominence (Phase 2).
Phase 3 adds evidence retrieval and verdicts here.

Run: python -m esg.workers.analyzer_worker
"""

from __future__ import annotations

import logging
import time

import psycopg

from .. import baseline, config, db, kafka_io
from ..claims.extract import ClaimExtractor, load_extractor

log = logging.getLogger("analyzer-worker")


def analyse(conn: psycopg.Connection, report_id: int, extractor: ClaimExtractor | None) -> None:
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
        claim_rows = None
        if extractor is not None:
            claim_rows = [
                (cl.chunk_id, cl.sentence.text, cl.sentence.start, cl.sentence.end,
                 cl.claim_score, cl.specificity_score, cl.prominence, extractor.model_name)
                for cl in extractor.extract(chunks)
            ]
        db.save_analysis(conn, report_id, baseline_rows, claim_rows)
    except Exception as exc:
        if db.is_connection_lost(conn):
            raise  # let db.Session reconnect and retry the job
        log.exception("Analysing report %s failed", report_id)
        db.set_status(conn, report_id, "FAILED", f"analyze: {exc}")
        return
    vague = sum(1 for r in claim_rows or [] if r[5] < 0.5)
    log.info("Report %s: %d chunks scored (%d flagged by baseline); %s claims (%d vague) in %.1fs",
             report_id, len(baseline_rows), sum(r[-1] for r in baseline_rows),
             "no" if claim_rows is None else len(claim_rows), vague, time.monotonic() - started)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    extractor = load_extractor()
    session = db.Session()
    kafka_io.run_consumer(config.TOPIC_REPORT_PARSED, "analyzer-workers",
                          lambda report_id: session.run(analyse, report_id, extractor))


if __name__ == "__main__":
    main()
