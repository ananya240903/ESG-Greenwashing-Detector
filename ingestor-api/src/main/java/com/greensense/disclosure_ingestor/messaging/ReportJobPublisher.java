package com.greensense.disclosure_ingestor.messaging;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class ReportJobPublisher {

    private final KafkaTemplate<String, ReportJob> kafka;
    private final String topic;

    public ReportJobPublisher(KafkaTemplate<String, ReportJob> kafka,
                              @Value("${app.kafka.topic.report-uploaded}") String topic) {
        this.kafka = kafka;
        this.topic = topic;
    }

    /** Keyed by report ID, so retries for one report land on the same partition. */
    public void publishUploaded(long reportId) {
        kafka.send(topic, String.valueOf(reportId), new ReportJob(reportId)).join();
    }
}
