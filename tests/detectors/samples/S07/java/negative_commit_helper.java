package com.example.consumer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class ShipmentConsumer {
    private final ExecutorService workers = Executors.newFixedThreadPool(4);
    private final KafkaConsumer<String, String> consumer;

    public ShipmentConsumer(Properties props) {
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        this.consumer = new KafkaConsumer<>(props);
    }

    public void run() throws Exception {
        consumer.subscribe(List.of("shipments"));
        while (true) {
            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(100));
            workers.submit(() -> handle(records)).get();
            markDone();
        }
    }

    private void markDone() {
        consumer.commitSync();
    }

    private void handle(ConsumerRecords<String, String> records) { }
}
