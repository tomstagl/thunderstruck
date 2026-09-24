package com.example.consumer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.TopicPartition;

// Offsets live in the application's database, written in the same transaction
// as the result, and the consumer seeks to them on start: exactly-once without
// Kafka commits.
public class LedgerConsumer {
    private final OffsetStore offsets;

    public LedgerConsumer(OffsetStore offsets) {
        this.offsets = offsets;
    }

    public void run(Properties props) {
        props.put("enable.auto.commit", "false");
        KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
        TopicPartition partition = new TopicPartition("ledger", 0);
        consumer.assign(List.of(partition));
        consumer.seek(partition, offsets.load(partition));
        while (true) {
            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(100));
            for (ConsumerRecord<String, String> record : records) {
                offsets.applyAndStore(record.value(), partition, record.offset() + 1);
            }
        }
    }
}

interface OffsetStore {
    long load(TopicPartition partition);
    void applyAndStore(String value, TopicPartition partition, long nextOffset);
}
