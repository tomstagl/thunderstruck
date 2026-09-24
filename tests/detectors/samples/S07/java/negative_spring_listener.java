package com.example.consumer;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class PaymentListener {
    @KafkaListener(topics = "payments", groupId = "billing")
    public void onPayment(ConsumerRecord<String, String> record, Acknowledgment ack) {
        settle(record.value());
        ack.acknowledge();
    }

    private void settle(String payment) { }
}
