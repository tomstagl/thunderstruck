package com.example.orders;

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    Page<Order> findByStatus(String status, Pageable pageable);
    Optional<Order> findByReference(String reference);
}

class Order { }

class OrderEvents {
    static java.util.Properties config() {
        java.util.Properties props = new java.util.Properties();
        props.put(org.apache.kafka.clients.consumer.ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
        return props;
    }

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
