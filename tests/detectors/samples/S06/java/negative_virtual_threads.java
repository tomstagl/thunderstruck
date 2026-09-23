package com.example.web;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

// A thread per task: nothing queues behind a fixed number of workers.
public class Handler {
    private final ExecutorService exec = Executors.newVirtualThreadPerTaskExecutor();

    public void handle(Runnable r) {
        exec.submit(r);
    }

    public void other(Runnable r) {
        exec.execute(r);
    }
}
