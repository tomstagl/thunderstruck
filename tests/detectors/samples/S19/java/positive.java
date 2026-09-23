package com.example.consumer;

public class OrderConsumer {
    public void handle(Runnable task) {
        try {
            task.run();
        } catch (Exception e) {
        }
    }

    public void handleQuietly(Runnable task) {
        try { task.run(); } catch (RuntimeException e) { }
    }

    public void handleBestEffort(Runnable task) {
        try {
            task.run();
        } catch (IllegalStateException e) { /* intentionally ignored: best effort */ }
    }
}
