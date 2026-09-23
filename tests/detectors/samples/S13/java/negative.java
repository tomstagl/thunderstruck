package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WorkerRegistry {
    private static final ExecutorService INTERACTIVE_POOL = Executors.newFixedThreadPool(10);
    private static final ExecutorService BATCH_POOL = Executors.newFixedThreadPool(4);

    public void submitInteractive(Runnable r) {
        INTERACTIVE_POOL.submit(r);
    }

    public void submitBatch(Runnable r) {
        BATCH_POOL.submit(r);
    }
}
