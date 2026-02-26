package com.greensense.disclosure_ingestor.repository;

import com.greensense.disclosure_ingestor.model.Disclosure;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public interface DisclosureRepository extends JpaRepository<Disclosure, Long> {
    // Spring Boot will automatically turn this into:
    // SELECT * FROM disclosure WHERE company_name = ?
    List<Disclosure> findByCompanyName(String companyName);
}