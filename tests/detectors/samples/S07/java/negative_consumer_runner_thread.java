package com.example.consumer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.errors.WakeupException;

// The KafkaConsumer javadoc's KafkaConsumerRunner: the poll loop runs on its
// own thread and processes each batch synchronously under auto-commit. Starting
// that thread (`new Thread(runner)`, `executor.submit(runner)`) and a shutdown
// hook are not hand-offs of the polled records.
public class KafkaConsumerRunner implements Runnable {
    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final KafkaConsumer<String, String> consumer;

    public KafkaConsumerRunner(KafkaConsumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public static void main(String[] args) {
        KafkaConsumerRunner runner = new KafkaConsumerRunner(new KafkaConsumer<>(new Properties()));
        new Thread(runner).start();
        Runtime.getRuntime().addShutdownHook(new Thread(runner::shutdown));
    }

    public static void startOn(ExecutorService executor, KafkaConsumerRunner runner) {
        executor.submit(runner);
    }

    @Override
    public void run() {
        try {
            consumer.subscribe(List.of("topic"));
            while (!closed.get()) {
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(10000));
                for (ConsumerRecord<String, String> record : records) {
                    handle(record);
                }
            }
        } catch (WakeupException e) {
            if (!closed.get()) throw e;
        } finally {
            consumer.close();
        }
    }

    public void shutdown() {
        closed.set(true);
        consumer.wakeup();
    }

    private void handle(ConsumerRecord<String, String> record) { }
}
