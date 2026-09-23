package com.example.metrics;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

// Each pool runs one fixed job the class itself defines; no caller's work
// queues behind another's.
public class MetricsFlusher implements Runnable {
    private final ScheduledExecutorService flusher = Executors.newSingleThreadScheduledExecutor();

    public void start() {
        flusher.scheduleAtFixedRate(this::flush, 10, 10, TimeUnit.SECONDS);
    }

    private void flush() { }

    public void run() { }
}

class ConsumerLoop implements Runnable {
    private final ExecutorService loop = Executors.newSingleThreadExecutor();

    void start() {
        loop.submit(this);
    }

    public void run() { }
}
