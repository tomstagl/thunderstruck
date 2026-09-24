package com.example.consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderConsumer {
    private static final Logger log = LoggerFactory.getLogger(OrderConsumer.class);

    public void handle(Runnable task) {
        try {
            task.run();
        } catch (Exception e) {
            log.error("task failed", e);
        }
    }

    public void sleepQuietly() {
        try {
            Thread.sleep(10);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
