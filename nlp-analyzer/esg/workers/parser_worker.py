"""Worker 1: report.uploaded -> parse and chunk the PDF, embed the chunks -> report.parsed.

Run: python -m esg.workers.parser_worker
"""

from __future__ import annotations

import logging
import time

import psycopg

from .. import config, db, kafka_io
from ..embedding import embed_passages
from ..parsing import parse_pdf

log = logging.getLogger("parser-worker")


def process(conn: psycopg.Connection, report_id: int) -> bool:
    """Parse one report. Returns True when it is ready for the analyzer."""
    report = db.get_report(conn, report_id)
    if report is None:
        log.warning("Report %s not found; skipping", report_id)
        return False
    db.set_status(conn, report_id, "PARSING")
    started = time.monotonic()
    try:
        page_count, chunks = parse_pdf(config.REPORTS_DIR / report["storage_key"])
        embeddings = embed_passages([c.text for c in chunks])
        db.replace_chunks(conn, report_id, page_count, chunks, embeddings)
    except Exception as exc:  # a bad PDF must not stop the worker
        if db.is_connection_lost(conn):
            raise  # let db.Session reconnect and retry the job
        log.exception("Parsing report %s failed", report_id)
        db.set_status(conn, report_id, "FAILED", f"parse: {exc}")
        return False
    log.info(
        "Report %s (%s %s): %d pages -> %d chunks in %.1fs",
        report_id, report["company"], report["fiscal_year"], page_count, len(chunks),
        time.monotonic() - started,
    )
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    session = db.Session()
    producer = kafka_io.make_producer()

    def handle(report_id: int) -> None:
        if session.run(process, report_id):
            kafka_io.publish_report_id(producer, config.TOPIC_REPORT_PARSED, report_id)

    kafka_io.run_consumer(config.TOPIC_REPORT_UPLOADED, "parser-workers", handle)


if __name__ == "__main__":
    main()
