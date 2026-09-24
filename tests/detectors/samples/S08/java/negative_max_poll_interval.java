package com.example.consumer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.springframework.jdbc.core.JdbcTemplate;

// Slow per-record work, with max.poll.interval.ms raised to fit it.
public class InvoiceLoader {
    private final JdbcTemplate jdbc;

    public InvoiceLoader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void run(Properties props) {
        props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 900_000);
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of("invoices"));
            while (true) {
                consumer.poll(Duration.ofSeconds(1)).forEach(r ->
                        jdbc.update("insert into invoice(id, body) values (?, ?)", r.key(), r.value()));
                consumer.commitSync();
            }
        }
    }
}
