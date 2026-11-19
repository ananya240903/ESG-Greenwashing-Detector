package com.greensense.disclosure_ingestor.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

/**
 * Two topics, one per hop: the API publishes report.uploaded (consumed by the parser
 * worker), and the parser worker publishes report.parsed (consumed by the analyzer worker).
 * Three partitions each, so up to three copies of each worker can share the load.
 */
@Configuration
public class KafkaConfig {

    @Bean
    public NewTopic reportUploadedTopic(@Value("${app.kafka.topic.report-uploaded}") String name) {
        return TopicBuilder.name(name).partitions(3).replicas(1).build();
    }

    @Bean
    public NewTopic reportParsedTopic(@Value("${app.kafka.topic.report-parsed}") String name) {
        return TopicBuilder.name(name).partitions(3).replicas(1).build();
    }
}
