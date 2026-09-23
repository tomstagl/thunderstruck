package com.example.consumer;

import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class OrderConsumer {
    private final KafkaConsumer<String, String> consumer;

    public OrderConsumer(KafkaConsumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public void run() {
        while (true) {
            ConsumerRecords<String, String> records = consumer.poll(java.time.Duration.ofMillis(100));
            process(records);
            consumer.commitSync();
        }
    }

    public void backfill(OrderApi api, int resumeFrom) {
        int page = resumeFrom;
        boolean hasMore = true;
        while (hasMore) {
            List<String> rows = api.list(page);
            hasMore = !rows.isEmpty();
            for (String row : rows) {
                insertRow(row);
            }
            page++;
            saveCursor(page);
        }
    }

    private void process(ConsumerRecords<String, String> records) { }
    private void insertRow(String row) { }
    private void saveCursor(int page) { }
}

interface OrderApi {
    List<String> list(int page);
}
