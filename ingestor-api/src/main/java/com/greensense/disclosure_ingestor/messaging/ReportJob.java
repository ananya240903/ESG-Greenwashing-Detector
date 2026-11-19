package com.greensense.disclosure_ingestor.messaging;

/** Kafka payload: only the report's ID. Workers read everything else from Postgres. */
public record ReportJob(long reportId) {
}
