package com.greensense.disclosure_ingestor.analysis;

import java.util.List;

/**
 * Read-only views of what the Python analyzer writes: claims, their evidence and verdicts,
 * and each report's risk score. The API serves these; it never writes them.
 */
public final class AnalysisViews {

    private AnalysisViews() {
    }

    /** One row of the report_risk view (db/init/002_report_risk.sql). */
    public record ReportRisk(long reportId, String company, int fiscalYear, int claims,
                             int substantiated, int vague, int unsupported, double riskScore) {
    }

    /** Where a passage sits in the report. */
    public record Location(String kind, String section, Integer principle, int page) {
    }

    public record Verdict(String label, Double confidence, String reason, List<Long> citedChunkIds,
                          String model) {
    }

    /** A passage retrieved as possible support; cited = the verdict's reason points to it. */
    public record Evidence(long chunkId, int rank, Location location, String text,
                           Double retrievalScore, Double rerankScore, boolean cited) {
    }

    public record Claim(long id, String sentence, Location location, double claimScore,
                        Double specificityScore, Double prominence, Verdict verdict,
                        List<Evidence> evidence) {
    }

    public record ReportClaims(long reportId, String company, int fiscalYear, ReportRisk risk,
                               List<Claim> claims) {
    }
}
