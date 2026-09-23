package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WorkerRegistry {
    private static final ExecutorService POOL = Executors.newFixedThreadPool(10);

    public void submitInteractive(Runnable r) {
        POOL.submit(r);
    }

    public void submitBatch(Runnable r) {
        POOL.submit(r);
    }
}
