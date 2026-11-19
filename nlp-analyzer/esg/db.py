"""Postgres access for the workers (psycopg 3 + pgvector)."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from . import config
from .parsing import Chunk

log = logging.getLogger(__name__)


def connect(retries: int = 30, delay: float = 2.0) -> psycopg.Connection:
    """Connect, waiting for Postgres to come up (it may start after the workers)."""
    for attempt in range(1, retries + 1):
        try:
            # autocommit: single statements commit at once, and `with conn.transaction()`
            # blocks are real transactions (not savepoints inside an implicit one).
            conn = psycopg.connect(config.DATABASE_URL, row_factory=dict_row, autocommit=True)
            register_vector(conn)
            return conn
        except psycopg.OperationalError as exc:
            if attempt == retries:
                raise
            log.info("Postgres not ready (%s); retry %d/%d", exc, attempt, retries)
            time.sleep(delay)
    raise AssertionError("unreachable")


def get_report(conn: psycopg.Connection, report_id: int) -> dict | None:
    return conn.execute("SELECT * FROM reports WHERE id = %s", (report_id,)).fetchone()


def set_status(conn: psycopg.Connection, report_id: int, status: str, error: str | None = None) -> None:
    conn.execute(
        "UPDATE reports SET status = %s, error = %s, updated_at = now() WHERE id = %s",
        (status, error, report_id),
    )


def replace_chunks(
    conn: psycopg.Connection,
    report_id: int,
    page_count: int,
    chunks: Sequence[Chunk],
    embeddings: np.ndarray | None,
) -> None:
    """Swap in a report's chunks atomically, so re-parsing a report is safe."""
    with conn.transaction():
        conn.execute("DELETE FROM chunks WHERE report_id = %s", (report_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (report_id, seq, kind, section, principle, heading,
                                       page_start, page_end, text, word_count, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (report_id, c.seq, c.kind, c.section, c.principle, c.heading,
                     c.page_start, c.page_end, c.text, c.word_count,
                     None if embeddings is None else embeddings[i])
                    for i, c in enumerate(chunks)
                ],
            )
        conn.execute(
            "UPDATE reports SET page_count = %s, status = 'PARSED', error = NULL, updated_at = now()"
            " WHERE id = %s",
            (page_count, report_id),
        )


def text_chunks(conn: psycopg.Connection, report_id: int) -> list[dict]:
    return conn.execute(
        "SELECT id, text FROM chunks WHERE report_id = %s AND kind = 'text' ORDER BY seq",
        (report_id,),
    ).fetchall()


def replace_baseline_scores(conn: psycopg.Connection, report_id: int, rows: Sequence[tuple]) -> None:
    """rows: (chunk_id, esg_label, esg_score, tone_label, tone_score, risk_score, flagged)."""
    with conn.transaction():
        conn.execute(
            "DELETE FROM baseline_scores WHERE chunk_id IN (SELECT id FROM chunks WHERE report_id = %s)",
            (report_id,),
        )
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO baseline_scores
                       (chunk_id, esg_label, esg_score, tone_label, tone_score, risk_score, flagged)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                rows,
            )
        conn.execute(
            "UPDATE reports SET status = 'ANALYZED', error = NULL, updated_at = now() WHERE id = %s",
            (report_id,),
        )
