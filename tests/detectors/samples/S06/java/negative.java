package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestQueue {
    private final ExecutorService interactivePool = Executors.newFixedThreadPool(8);
    private final ExecutorService batchPool = Executors.newFixedThreadPool(2);

    public void submitInteractive(Runnable task) {
        interactivePool.submit(task);
    }

    public void submitBatch(Runnable task) {
        batchPool.submit(task);
    }
}
