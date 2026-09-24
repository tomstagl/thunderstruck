package com.example.orders;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByStatus(String status);
}

class Order { }

class OrderEvents {
    void run(org.apache.kafka.clients.consumer.KafkaConsumer<String, String> consumer) {
        while (true) {
            consumer.poll(java.time.Duration.ofMillis(100)).forEach(r -> handle(r.value()));
        }
    }

    private void handle(String value) {
        audit.postForObject("http://audit/events", value, String.class);
    }

    private final org.springframework.web.client.RestTemplate audit =
            new org.springframework.web.client.RestTemplate();
}
