package com.greensense.disclosure_ingestor.model;

/** Pipeline stage of a report. Must match the CHECK constraint on reports.status. */
public enum ReportStatus {
    UPLOADED, PARSING, PARSED, ANALYZING, ANALYZED, FAILED
}
