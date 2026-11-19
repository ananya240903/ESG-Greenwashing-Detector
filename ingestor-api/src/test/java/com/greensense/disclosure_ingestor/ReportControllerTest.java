package com.greensense.disclosure_ingestor;

import com.greensense.disclosure_ingestor.messaging.ReportJobPublisher;
import com.greensense.disclosure_ingestor.repository.ReportRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ReportControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportRepository repository;

    @MockitoBean
    ReportJobPublisher publisher;

    @BeforeEach
    void clean() {
        repository.deleteAll();
    }

    private static MockMultipartFile pdf(String body) {
        return new MockMultipartFile("file", "brsr.pdf", "application/pdf",
                ("%PDF-1.7\n" + body).getBytes(StandardCharsets.US_ASCII));
    }

    @Test
    void uploadStoresReportAndQueuesIt() throws Exception {
        mvc.perform(multipart("/api/reports").file(pdf("a"))
                        .param("company", "  Tata Steel ").param("fiscalYear", "2024"))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.company").value("Tata Steel"))
                .andExpect(jsonPath("$.fiscalYear").value(2024))
                .andExpect(jsonPath("$.status").value("UPLOADED"))
                .andExpect(jsonPath("$.storageKey").doesNotExist());

        long id = repository.findAll().get(0).getId();
        verify(publisher).publishUploaded(id);
    }

    @Test
    void sameFileTwiceReturnsExistingReportWithoutRequeueing() throws Exception {
        mvc.perform(multipart("/api/reports").file(pdf("same"))
                .param("company", "HUL").param("fiscalYear", "2024")).andExpect(status().isAccepted());
        mvc.perform(multipart("/api/reports").file(pdf("same"))
                        .param("company", "HUL").param("fiscalYear", "2024"))
                .andExpect(status().isOk());

        verify(publisher, times(1)).publishUploaded(anyLong());
        org.assertj.core.api.Assertions.assertThat(repository.count()).isEqualTo(1);
    }

    @Test
    void rejectsNonPdf() throws Exception {
        MockMultipartFile txt = new MockMultipartFile("file", "x.pdf", "application/pdf", "hello".getBytes());
        mvc.perform(multipart("/api/reports").file(txt).param("company", "X").param("fiscalYear", "2024"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(publisher);
    }

    @Test
    void rejectsBadYearAndBlankCompany() throws Exception {
        mvc.perform(multipart("/api/reports").file(pdf("b")).param("company", "X").param("fiscalYear", "1990"))
                .andExpect(status().isBadRequest());
        mvc.perform(multipart("/api/reports").file(pdf("c")).param("company", " ").param("fiscalYear", "2024"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void reprocessRequeues() throws Exception {
        mvc.perform(multipart("/api/reports").file(pdf("d"))
                .param("company", "NTPC").param("fiscalYear", "2024")).andExpect(status().isAccepted());
        long id = repository.findAll().get(0).getId();

        mvc.perform(post("/api/reports/{id}/reprocess", id)).andExpect(status().isAccepted());
        verify(publisher, times(2)).publishUploaded(id);
    }

    @Test
    void listFiltersByCompanyAndMissingIs404() throws Exception {
        mvc.perform(multipart("/api/reports").file(pdf("e"))
                .param("company", "Axis Bank").param("fiscalYear", "2024")).andExpect(status().isAccepted());

        mvc.perform(get("/api/reports").param("company", "axis"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(1));
        mvc.perform(get("/api/reports").param("company", "wipro"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
        mvc.perform(get("/api/reports/{id}", 999_999)).andExpect(status().isNotFound());
    }
}
