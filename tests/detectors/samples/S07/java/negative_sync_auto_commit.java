package com.example.consumer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

// The KafkaConsumer javadoc's "automatic offset committing" loop. Records are
// processed on the polling thread, and poll() auto-commits only the offsets the
// previous poll returned, which this loop has already processed. That is
// at-least-once delivery, the same guarantee a manual commitSync() gives.
public class AuditLogConsumer {
    public void run(Properties props) {
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "true");
        props.put(ConsumerConfig.AUTO_COMMIT_INTERVAL_MS_CONFIG, "1000");
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of("audit"));
            while (true) {
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(100));
                for (ConsumerRecord<String, String> record : records) {
                    System.out.printf("offset = %d, key = %s%n", record.offset(), record.key());
                }
            }
        }
    }
}
