package com.greensense.disclosure_ingestor.repository;

import com.greensense.disclosure_ingestor.model.Report;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface ReportRepository extends JpaRepository<Report, Long> {

    Optional<Report> findBySha256(String sha256);

    List<Report> findByCompanyContainingIgnoreCaseOrderByFiscalYearDesc(String company);

    List<Report> findAllByOrderByCreatedAtDesc();
}
