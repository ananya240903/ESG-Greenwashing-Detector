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

    /**
     * A passage retrieved as possible support; cited = the verdict's reason points to it.
     * ownPassage = the passage the claim itself comes from. The models saw it with the claim
     * sentence cut out; text here is the whole passage, claim included.
     */
    public record Evidence(long chunkId, int rank, Location location, String text,
                           Double retrievalScore, Double rerankScore, boolean cited, boolean ownPassage) {
    }

    /** topics: BRSR topic keys (ghg, water, energy, waste are SEBI BRSR Core attributes). */
    public record Claim(long id, String sentence, Location location, double claimScore,
                        Double specificityScore, Double prominence, List<String> topics, Verdict verdict,
                        List<Evidence> evidence) {
    }

    public record ReportClaims(long reportId, String company, int fiscalYear, ReportRisk risk,
                               List<Claim> claims) {
    }
}
