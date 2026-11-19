package com.greensense.disclosure_ingestor.service;

import com.greensense.disclosure_ingestor.messaging.ReportJobPublisher;
import com.greensense.disclosure_ingestor.model.Report;
import com.greensense.disclosure_ingestor.model.ReportStatus;
import com.greensense.disclosure_ingestor.repository.ReportRepository;
import com.greensense.disclosure_ingestor.storage.ReportStorage;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;

@Service
public class ReportService {

    private final ReportRepository repository;
    private final ReportStorage storage;
    private final ReportJobPublisher publisher;

    public ReportService(ReportRepository repository, ReportStorage storage, ReportJobPublisher publisher) {
        this.repository = repository;
        this.storage = storage;
        this.publisher = publisher;
    }

    /** created = false means the same PDF was uploaded before; the existing report is returned. */
    public record UploadResult(Report report, boolean created) {
    }

    /**
     * Stores the PDF, records it, then queues it. The row is committed before the Kafka
     * message is sent, so the parser worker always finds the report it is told about.
     * If sending fails, the report stays UPLOADED and can be re-queued with reprocess().
     */
    public UploadResult upload(MultipartFile file, String company, int fiscalYear) {
        ReportStorage.StoredFile stored = storage.store(file);

        Optional<Report> existing = repository.findBySha256(stored.sha256());
        if (existing.isPresent()) {
            storage.delete(stored.key());
            return new UploadResult(existing.get(), false);
        }

        Report report = new Report();
        report.setCompany(company.strip());
        report.setFiscalYear(fiscalYear);
        report.setOriginalFilename(Optional.ofNullable(file.getOriginalFilename()).orElse("report.pdf"));
        report.setStorageKey(stored.key());
        report.setSha256(stored.sha256());
        report = repository.save(report);

        publisher.publishUploaded(report.getId());
        return new UploadResult(report, true);
    }

    /** Puts a report back at the start of the pipeline, e.g. after a parser fix or a failure. */
    public Report reprocess(long id) {
        Report report = get(id);
        report.setStatus(ReportStatus.UPLOADED);
        report.setError(null);
        report = repository.save(report);
        publisher.publishUploaded(report.getId());
        return report;
    }

    public Report get(long id) {
        return repository.findById(id).orElseThrow(() -> new NoSuchElementException("No report " + id));
    }

    public List<Report> list(String company) {
        return company == null || company.isBlank()
                ? repository.findAllByOrderByCreatedAtDesc()
                : repository.findByCompanyContainingIgnoreCaseOrderByFiscalYearDesc(company.strip());
    }
}
