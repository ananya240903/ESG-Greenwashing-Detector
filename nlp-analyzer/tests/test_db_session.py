"""db.Session reconnects after a dropped connection, and only then."""

import psycopg
import pytest

from esg.db import Session


class FakeConn:
    def __init__(self):
        self.closed = False
        self.broken = False


def make_session():
    made = []

    def connect():
        made.append(FakeConn())
        return made[-1]

    return Session(connect_fn=connect, attempts=3), made


def test_reconnects_and_retries_when_connection_drops():
    session, made = make_session()
    calls = []

    def job(conn, x):
        calls.append(conn)
        if len(calls) == 1:
            conn.broken = True  # what psycopg sets when the server goes away
            raise psycopg.OperationalError("terminating connection due to administrator command")
        return x * 2

    assert session.run(job, 21) == 42
    assert len(made) == 2 and calls == made


def test_sql_errors_on_a_healthy_connection_are_not_retried():
    session, made = make_session()

    def job(conn):
        raise psycopg.OperationalError("canceling statement due to statement timeout")

    with pytest.raises(psycopg.OperationalError):
        session.run(job)
    assert len(made) == 1


def test_gives_up_after_the_last_attempt():
    session, made = make_session()

    def job(conn):
        conn.broken = True
        raise psycopg.OperationalError("server closed the connection unexpectedly")

    with pytest.raises(psycopg.OperationalError):
        session.run(job)
    assert len(made) == 3


def test_connection_is_reused_between_jobs():
    session, made = make_session()
    session.run(lambda conn: None)
    session.run(lambda conn: None)
    assert len(made) == 1
