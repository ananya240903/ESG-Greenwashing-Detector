package com.greensense.disclosure_ingestor.analysis;

import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Claim;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Evidence;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Location;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.ReportRisk;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Verdict;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** Plain SQL over the analyzer's tables; they are written by the Python workers, not JPA. */
@Repository
public class AnalysisRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public AnalysisRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static final String RISK_SQL = """
            SELECT report_id, company, fiscal_year, claims, substantiated, vague, unsupported, risk_score
            FROM report_risk""";

    private static final RowMapper<ReportRisk> RISK = (rs, row) -> mapRisk(rs);

    private static ReportRisk mapRisk(ResultSet rs) throws SQLException {
        return new ReportRisk(rs.getLong("report_id"), rs.getString("company"), rs.getInt("fiscal_year"),
                rs.getInt("claims"), rs.getInt("substantiated"), rs.getInt("vague"),
                rs.getInt("unsupported"), rs.getDouble("risk_score"));
    }

    public List<ReportRisk> risk() {
        return jdbc.query(RISK_SQL + " ORDER BY risk_score DESC, company", RISK);
    }

    public Optional<ReportRisk> risk(long reportId) {
        return jdbc.query(RISK_SQL + " WHERE report_id = :id", Map.of("id", reportId), RISK)
                .stream().findFirst();
    }

    /** A report's claims in reading order, each with its verdict and ranked evidence. */
    public List<Claim> claims(long reportId, String verdictLabel) {
        var params = new MapSqlParameterSource("id", reportId).addValue("label", verdictLabel);
        Map<Long, ClaimRow> rows = new LinkedHashMap<>();
        jdbc.query("""
                SELECT c.id, c.sentence, c.claim_score, c.specificity_score, c.prominence,
                       ch.kind, ch.section, ch.principle, ch.page_start,
                       v.label, v.confidence, v.reason, v.cited_chunk_ids, v.model
                FROM claims c
                JOIN chunks ch ON ch.id = c.chunk_id
                LEFT JOIN verdicts v ON v.claim_id = c.id
                WHERE c.report_id = :id AND (CAST(:label AS TEXT) IS NULL OR v.label = :label)
                ORDER BY ch.seq, c.char_start""", params, rs -> {
            List<Long> cited = longs(rs.getArray("cited_chunk_ids"));
            Verdict verdict = rs.getString("label") == null ? null : new Verdict(rs.getString("label"),
                    nullableDouble(rs, "confidence"), rs.getString("reason"), cited, rs.getString("model"));
            rows.put(rs.getLong("id"), new ClaimRow(rs.getLong("id"), rs.getString("sentence"), location(rs),
                    rs.getDouble("claim_score"), nullableDouble(rs, "specificity_score"),
                    nullableDouble(rs, "prominence"), verdict, new ArrayList<>()));
        });
        if (rows.isEmpty()) {
            return List.of();
        }
        jdbc.query("""
                SELECT e.claim_id, e.chunk_id, e.rank, e.retrieval_score, e.rerank_score,
                       ch.kind, ch.section, ch.principle, ch.page_start, ch.text
                FROM evidence e
                JOIN chunks ch ON ch.id = e.chunk_id
                JOIN claims c ON c.id = e.claim_id
                WHERE c.report_id = :id
                ORDER BY e.claim_id, e.rank""", params, rs -> {
            ClaimRow claim = rows.get(rs.getLong("claim_id"));
            if (claim == null) {
                return;  // filtered out by verdict
            }
            long chunkId = rs.getLong("chunk_id");
            boolean cited = claim.verdict() != null && claim.verdict().citedChunkIds().contains(chunkId);
            claim.evidence().add(new Evidence(chunkId, rs.getInt("rank"), location(rs), rs.getString("text"),
                    nullableDouble(rs, "retrieval_score"), nullableDouble(rs, "rerank_score"), cited));
        });
        return rows.values().stream().map(ClaimRow::toClaim).toList();
    }

    private record ClaimRow(long id, String sentence, Location location, double claimScore,
                            Double specificityScore, Double prominence, Verdict verdict,
                            List<Evidence> evidence) {
        Claim toClaim() {
            return new Claim(id, sentence, location, claimScore, specificityScore, prominence, verdict,
                    List.copyOf(evidence));
        }
    }

    private static Location location(ResultSet rs) throws SQLException {
        int value = rs.getInt("principle");
        Integer principle = rs.wasNull() ? null : value;  // wasNull() refers to the last column read
        return new Location(rs.getString("kind"), rs.getString("section"), principle, rs.getInt("page_start"));
    }

    private static Double nullableDouble(ResultSet rs, String column) throws SQLException {
        double v = rs.getDouble(column);
        return rs.wasNull() ? null : v;
    }

    private static List<Long> longs(Array array) throws SQLException {
        if (array == null) {
            return List.of();
        }
        Object[] values = (Object[]) array.getArray();
        return Arrays.stream(values).map(v -> ((Number) v).longValue()).toList();
    }
}
