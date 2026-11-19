"""Kafka plumbing shared by the workers.

Messages carry only a report ID, as JSON: {"reportId": 42}. All data lives in Postgres.
Offsets are committed only after a message has been handled, so a crashed worker
re-processes the message on restart; the handlers are idempotent, so that is safe.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from confluent_kafka import Consumer, KafkaException, Producer

from . import config

log = logging.getLogger(__name__)


def make_producer() -> Producer:
    return Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP})


def publish_report_id(producer: Producer, topic: str, report_id: int) -> None:
    producer.produce(topic, key=str(report_id), value=json.dumps({"reportId": report_id}))
    producer.flush(10)


def run_consumer(topic: str, group_id: str, handle: Callable[[int], None]) -> None:
    """Call `handle(report_id)` for every message on `topic`, forever."""
    consumer = Consumer({
        "bootstrap.servers": config.KAFKA_BOOTSTRAP,
        "group.id": group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        # Parsing a long PDF or scoring hundreds of chunks can take minutes.
        "max.poll.interval.ms": 30 * 60 * 1000,
    })
    consumer.subscribe([topic])
    log.info("Listening on %s as %s", topic, group_id)
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().fatal():
                    raise KafkaException(msg.error())
                log.warning("Kafka error: %s", msg.error())
                continue
            try:
                report_id = int(json.loads(msg.value())["reportId"])
            except (ValueError, KeyError, TypeError) as exc:
                log.error("Skipping malformed message %r: %s", msg.value(), exc)
            else:
                handle(report_id)
            consumer.commit(message=msg, asynchronous=False)
    except KeyboardInterrupt:
        log.info("Stopping")
    finally:
        consumer.close()
