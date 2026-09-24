package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestQueue {
    private final ExecutorService pool = Executors.newFixedThreadPool(8);

    public void submit(Runnable task) {
        pool.submit(task);
    }
}
