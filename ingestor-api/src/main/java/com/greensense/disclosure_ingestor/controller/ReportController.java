package com.greensense.disclosure_ingestor.controller;

import com.greensense.disclosure_ingestor.model.Report;
import com.greensense.disclosure_ingestor.model.ReportStatus;
import com.greensense.disclosure_ingestor.service.ReportService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.OffsetDateTime;
import java.util.List;

@RestController
@RequestMapping("/api/reports")
@Validated
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    /** What clients see of a report (the storage key and hash stay internal). */
    public record ReportResponse(long id, String company, int fiscalYear, String originalFilename,
                                 Integer pageCount, ReportStatus status, String error,
                                 OffsetDateTime createdAt, OffsetDateTime updatedAt) {
        static ReportResponse of(Report r) {
            return new ReportResponse(r.getId(), r.getCompany(), r.getFiscalYear(), r.getOriginalFilename(),
                    r.getPageCount(), r.getStatus(), r.getError(), r.getCreatedAt(), r.getUpdatedAt());
        }
    }

    /**
     * Upload a BRSR PDF. fiscalYear is the year the financial year ends (FY2023-24 is 2024).
     * 202 when queued; 200 with the existing report when the same file was uploaded before.
     */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ReportResponse> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam("company") @NotBlank @Size(max = 200) String company,
            @RequestParam("fiscalYear") @Min(2000) @Max(2100) int fiscalYear) {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("Empty file");
        }
        ReportService.UploadResult result = service.upload(file, company, fiscalYear);
        HttpStatus status = result.created() ? HttpStatus.ACCEPTED : HttpStatus.OK;
        return ResponseEntity.status(status).body(ReportResponse.of(result.report()));
    }

    @GetMapping
    public List<ReportResponse> list(@RequestParam(required = false) String company) {
        return service.list(company).stream().map(ReportResponse::of).toList();
    }

    @GetMapping("/{id}")
    public ReportResponse get(@PathVariable long id) {
        return ReportResponse.of(service.get(id));
    }

    @PostMapping("/{id}/reprocess")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ReportResponse reprocess(@PathVariable long id) {
        return ReportResponse.of(service.reprocess(id));
    }
}
