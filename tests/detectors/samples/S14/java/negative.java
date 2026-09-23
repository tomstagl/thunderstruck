package com.example.workers;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPool {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4, 4, 60, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(200),
            new ThreadPoolExecutor.CallerRunsPolicy());
    private final LinkedBlockingQueue<Runnable> inbox = new LinkedBlockingQueue<>(1000);
}
