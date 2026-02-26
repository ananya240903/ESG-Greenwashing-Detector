package com.greensense.disclosure_ingestor.model;

import jakarta.persistence.*;
import lombok.Data;
import com.fasterxml.jackson.annotation.JsonProperty;

@Entity
@Data
public class Disclosure {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JsonProperty("company") // This maps the JSON "company" to Java "companyName"
    private String companyName;

    @Column(columnDefinition = "TEXT")
    private String content;
}