package com.example.rpc;

import static java.util.concurrent.Executors.newFixedThreadPool;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

// Two pools: the second is created through a static import.
public class RpcServer {
    private final ExecutorService metrics = Executors.newScheduledThreadPool(1);
    private final ExecutorService rpc = newFixedThreadPool(8);

    public void handle(Runnable r) {
        rpc.submit(r);
    }
}
