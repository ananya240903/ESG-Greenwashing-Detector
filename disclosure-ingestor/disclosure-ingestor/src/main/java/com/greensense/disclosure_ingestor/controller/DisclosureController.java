package com.greensense.disclosure_ingestor.controller;

import com.greensense.disclosure_ingestor.model.Disclosure;
import com.greensense.disclosure_ingestor.service.DisclosureService; // Import the new service
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/disclosures")
public class DisclosureController {

    private final DisclosureService disclosureService;

    // We inject the Service here instead of the Repository
    public DisclosureController(DisclosureService disclosureService) {
        this.disclosureService = disclosureService;
    }

    @PostMapping
    public List<Disclosure> uploadBulk(@RequestBody List<Disclosure> disclosures) {
        // Change parameter to List<Disclosure> to match Postman JSON array
        return disclosureService.saveAndProduceAll(disclosures);
    }

    @GetMapping
    public List<Disclosure> getAll() {
        // You can add a method in DisclosureService to call repository.findAll()
        return disclosureService.getAllDisclosures();
    }

    @GetMapping("/search")
    public List<Disclosure> searchByCompany(@RequestParam String name) {
        return disclosureService.searchByCompany(name);
    }
}