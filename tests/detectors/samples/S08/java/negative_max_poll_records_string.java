package com.example.consumer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.springframework.web.client.RestTemplate;

// Slow per-record work, with the batch bounded by the property's string name.
public class WebhookRelay {
    private final RestTemplate http = new RestTemplate();

    public void run(Properties props) {
        props.put("max.poll.records", "20");
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of("webhooks"));
            while (true) {
                consumer.poll(Duration.ofSeconds(1)).forEach(r ->
                        http.postForEntity(r.key(), r.value(), Void.class));
                consumer.commitSync();
            }
        }
    }
}
