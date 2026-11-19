"""Worker 2: report.parsed -> score the report's chunks.

For now this runs the FinBERT baseline over every text chunk. Phase 2 adds the claim
and specificity classifiers here; Phase 3 adds evidence retrieval and verdicts.

Run: python -m esg.workers.analyzer_worker
"""

from __future__ import annotations

import logging
import time

from .. import baseline, config, db, kafka_io

log = logging.getLogger("analyzer-worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    conn = db.connect()

    def handle(report_id: int) -> None:
        if db.get_report(conn, report_id) is None:
            log.warning("Report %s not found; skipping", report_id)
            return
        db.set_status(conn, report_id, "ANALYZING")
        started = time.monotonic()
        try:
            chunks = db.text_chunks(conn, report_id)
            scores = baseline.score_texts([c["text"] for c in chunks])
            rows = [
                (c["id"], s.esg_label, s.esg_score, s.tone_label, s.tone_score, s.risk_score, s.flagged)
                for c, s in zip(chunks, scores)
            ]
            db.replace_baseline_scores(conn, report_id, rows)
        except Exception as exc:
            conn.rollback()
            log.exception("Analysing report %s failed", report_id)
            db.set_status(conn, report_id, "FAILED", f"analyze: {exc}")
            return
        flagged = sum(r[-1] for r in rows)
        log.info("Report %s: scored %d chunks, %d flagged, in %.1fs",
                 report_id, len(rows), flagged, time.monotonic() - started)

    kafka_io.run_consumer(config.TOPIC_REPORT_PARSED, "analyzer-workers", handle)


if __name__ == "__main__":
    main()
