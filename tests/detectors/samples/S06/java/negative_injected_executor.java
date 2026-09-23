package com.example.orders;

import java.util.concurrent.ExecutorService;

// The executor is created and sized elsewhere; this class only uses it, and
// holds no pool of its own to separate.
public class OrderService {
    private final ExecutorService executor;

    public OrderService(ExecutorService executor) {
        this.executor = executor;
    }

    public void place(Runnable r) {
        executor.submit(r);
    }

    public void cancel(Runnable r) {
        executor.submit(r);
    }

    static void shutdownQuietly(ExecutorService es) {
        es.shutdown();
    }
}
