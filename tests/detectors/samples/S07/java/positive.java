package com.example.consumer;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class OrderConsumer {
    private final KafkaConsumer<String, String> consumer;
    private final ExecutorService workers = Executors.newFixedThreadPool(4);

    public OrderConsumer(KafkaConsumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public void run() {
        while (true) {
            ConsumerRecords<String, String> records = consumer.poll(java.time.Duration.ofMillis(100));
            workers.submit(() -> process(records));
        }
    }

    public void backfill(OrderApi api) {
        int page = 0;
        boolean hasMore = true;
        while (hasMore) {
            List<String> rows = api.list(page);
            hasMore = !rows.isEmpty();
            for (String row : rows) {
                insertRow(row);
            }
            page++;
        }
    }

    private void process(ConsumerRecords<String, String> records) { }
    private void insertRow(String row) { }
}

interface OrderApi {
    List<String> list(int page);
}

class RabbitOrders {
    void start(com.rabbitmq.client.Channel channel, com.rabbitmq.client.Consumer consumer) throws Exception {
        channel.basicConsume("orders", true, consumer);
    }
}
