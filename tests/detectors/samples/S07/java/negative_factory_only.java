package com.example.consumer;

import java.util.Properties;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Builds a consumer but never polls it; the only poll() here is a
// BlockingQueue's (no argument, or a timeout and a unit).
@Configuration
public class ConsumerConfiguration {
    private final BlockingQueue<Runnable> tasks = new LinkedBlockingQueue<>();

    @Bean
    public KafkaConsumer<String, String> orderConsumer(Properties props) {
        return new KafkaConsumer<>(props);
    }

    public void drain(ExecutorService executor) throws InterruptedException {
        Runnable next = tasks.poll(1, TimeUnit.SECONDS);
        while (next != null) {
            executor.submit(next);
            next = tasks.poll();
        }
    }
}
