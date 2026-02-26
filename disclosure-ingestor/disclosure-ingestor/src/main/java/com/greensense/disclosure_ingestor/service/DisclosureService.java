package com.greensense.disclosure_ingestor.service;

import com.greensense.disclosure_ingestor.model.Disclosure;
import com.greensense.disclosure_ingestor.repository.DisclosureRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.stream.Collectors; // Required for bulk processing

@Service
public class DisclosureService {

    @Autowired
    private DisclosureRepository repository;

    @Autowired
    private KafkaTemplate<String, Disclosure> kafkaTemplate;

    /**
     * Processes a single disclosure: Saves to DB and sends to Kafka.
     */
    public Disclosure saveAndProduce(Disclosure disclosure) {
        // 1. Save to Database
        Disclosure savedDisclosure = repository.save(disclosure);

        // 2. Produce to Kafka Topic
        // Make sure this matches your Python Analyzer topic if needed
        kafkaTemplate.send("esg-disclosures", savedDisclosure);

        return savedDisclosure;
    }

    /**
     * NEW: Processes a list of disclosures (Bulk Upload).
     * This resolves the "Cannot resolve method" error in DisclosureController.
     */
    public List<Disclosure> saveAndProduceAll(List<Disclosure> disclosures) {
        return disclosures.stream()
                .map(this::saveAndProduce) // Loops through each item and calls single-item logic
                .collect(Collectors.toList()); // Gathers results back into a list
    }

    public List<Disclosure> getAllDisclosures() {
        return repository.findAll(); // Returns all records from the DB
    }

    public List<Disclosure> searchByCompany(String name) {
        return repository.findByCompanyName(name); // Searches by the 'company' field
    }
}