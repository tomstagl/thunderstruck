package com.example.workers;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

// The pool runs this class's own job, a Runnable held in a field. No caller
// hands it work to prioritise.
public class ConsumerRunner {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Runnable pollLoop = this::poll;

    public void start() {
        executor.submit(pollLoop);
    }

    private void poll() { }
}

