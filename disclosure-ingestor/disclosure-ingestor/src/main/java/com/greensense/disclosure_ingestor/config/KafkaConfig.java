package com.greensense.disclosure_ingestor.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaConfig {

    @Bean
    public NewTopic esgDisclosuresTopic() {
        return TopicBuilder.name("esg-disclosures")
                .partitions(3)
                .replicas(1)
                .build();
    }
}