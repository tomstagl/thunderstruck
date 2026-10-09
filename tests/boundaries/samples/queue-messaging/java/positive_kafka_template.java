import org.springframework.kafka.core.KafkaTemplate;

class Publisher {
    private final KafkaTemplate<String, String> kafka;

    void publish(String event) {
        kafka.send("events", event);  // boundary: queue/messaging
    }
}
