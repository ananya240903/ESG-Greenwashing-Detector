package com.greensense.disclosure_ingestor;

import com.greensense.disclosure_ingestor.analysis.AnalysisRepository;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Claim;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Evidence;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Location;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.ReportRisk;
import com.greensense.disclosure_ingestor.analysis.AnalysisViews.Verdict;
import com.greensense.disclosure_ingestor.messaging.ReportJobPublisher;
import com.greensense.disclosure_ingestor.model.Report;
import com.greensense.disclosure_ingestor.repository.ReportRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Optional;

import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** The analysis endpoints; the SQL repository is mocked (H2 has no analyzer tables). */
@SpringBootTest
@AutoConfigureMockMvc
class AnalysisControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportRepository reports;

    @MockitoBean
    AnalysisRepository analysis;

    @MockitoBean
    ReportJobPublisher publisher;

    long reportId;

    @BeforeEach
    void setUp() {
        reports.deleteAll();
        Report r = new Report();
        r.setCompany("NTPC");
        r.setFiscalYear(2024);
        r.setOriginalFilename("ntpc.pdf");
        r.setStorageKey("k-" + System.nanoTime());
        r.setSha256("a".repeat(64));
        reportId = reports.save(r).getId();
    }

    @Test
    void riskListsReports() throws Exception {
        when(analysis.risk()).thenReturn(List.of(new ReportRisk(reportId, "NTPC", 2024, 25, 13, 5, 7, 48.0)));
        mvc.perform(get("/api/reports/risk"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].company").value("NTPC"))
                .andExpect(jsonPath("$[0].riskScore").value(48.0));
    }

    @Test
    void claimsComeWithVerdictAndEvidence() throws Exception {
        var evidence = new Evidence(91, 1, new Location("table", "A", null, 8), "| Trees planted | 39 million |",
                0.03, 6.2, true);
        var claim = new Claim(7, "We have planted 39 million trees so far.", new Location("text", "C", 6, 31),
                0.98, 1.0, 1.0,
                new Verdict("substantiated", 0.94, "Backed by table, Section A, p. 8 (entailment 0.94).",
                        List.of(91L), "m"),
                List.of(evidence));
        when(analysis.claims(reportId, null)).thenReturn(List.of(claim));
        when(analysis.risk(reportId)).thenReturn(Optional.of(new ReportRisk(reportId, "NTPC", 2024, 1, 1, 0, 0, 0)));

        mvc.perform(get("/api/reports/{id}/claims", reportId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.company").value("NTPC"))
                .andExpect(jsonPath("$.risk.claims").value(1))
                .andExpect(jsonPath("$.claims[0].verdict.label").value("substantiated"))
                .andExpect(jsonPath("$.claims[0].location.principle").value(6))
                .andExpect(jsonPath("$.claims[0].evidence[0].cited").value(true))
                .andExpect(jsonPath("$.claims[0].evidence[0].location.page").value(8));
    }

    @Test
    void verdictFilterIsPassedThroughAndValidated() throws Exception {
        when(analysis.claims(reportId, "vague")).thenReturn(List.of());
        mvc.perform(get("/api/reports/{id}/claims", reportId).param("verdict", "vague"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.claims").isEmpty());
        verify(analysis).claims(reportId, "vague");

        mvc.perform(get("/api/reports/{id}/claims", reportId).param("verdict", "greenwashed"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unknownReportIs404() throws Exception {
        mvc.perform(get("/api/reports/{id}/claims", 999_999)).andExpect(status().isNotFound());
        verify(analysis, never()).claims(anyLong(), anyString());
    }
}
