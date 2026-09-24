package com.example.consumer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

// A poll loop whose per-record work is cheap and local. The default
// max.poll.records (500) already bounds each batch, and 500 prints never come
// near max.poll.interval.ms.
public class ResultPrinter {
    public void run(Properties props) {
        try (KafkaConsumer<String, Long> consumer = new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of("word-counts"));
            while (true) {
                ConsumerRecords<String, Long> records = consumer.poll(Duration.ofMillis(500));
                for (ConsumerRecord<String, Long> record : records) {
                    System.out.println(record.key() + " = " + record.value());
                }
            }
        }
    }
}
