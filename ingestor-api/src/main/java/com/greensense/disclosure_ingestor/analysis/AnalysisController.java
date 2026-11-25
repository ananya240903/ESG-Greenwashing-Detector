package com.greensense.disclosure_ingestor.analysis;

import com.greensense.disclosure_ingestor.analysis.AnalysisViews.ReportClaims;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.ReportRisk;
import com.greensense.disclosure_ingestor.model.Report;
import com.greensense.disclosure_ingestor.service.ReportService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Set;

/** What the analyzer found: risk scores per report, and each report's claims with evidence. */
@RestController
@RequestMapping("/api/reports")
public class AnalysisController {

    static final Set<String> VERDICTS = Set.of("substantiated", "vague", "unsupported");

    private final AnalysisRepository analysis;
    private final ReportService reports;

    public AnalysisController(AnalysisRepository analysis, ReportService reports) {
        this.analysis = analysis;
        this.reports = reports;
    }

    /** Every analysed report, riskiest first. */
    @GetMapping("/risk")
    public List<ReportRisk> risk() {
        return analysis.risk();
    }

    static final Set<String> TOPICS = Set.of("ghg", "water", "energy", "waste", "biodiversity", "air", "sourcing");

    /**
     * A report's claims in reading order. ?verdict=vague|unsupported|substantiated and
     * ?topic=ghg|water|energy|waste|biodiversity|air|sourcing filter them.
     */
    @GetMapping("/{id}/claims")
    public ReportClaims claims(@PathVariable long id, @RequestParam(required = false) String verdict,
                               @RequestParam(required = false) String topic) {
        if (verdict != null && !VERDICTS.contains(verdict)) {
            throw new IllegalArgumentException("verdict must be one of " + VERDICTS);
        }
        if (topic != null && !TOPICS.contains(topic)) {
            throw new IllegalArgumentException("topic must be one of " + TOPICS);
        }
        Report report = reports.get(id);  // 404 when the report does not exist
        return new ReportClaims(report.getId(), report.getCompany(), report.getFiscalYear(),
                analysis.risk(id).orElse(null), analysis.claims(id, verdict, topic));
    }
}
