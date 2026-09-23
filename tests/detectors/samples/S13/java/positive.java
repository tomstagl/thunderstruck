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

class InventoryActor extends akka.actor.AbstractActor {
    @Override
    public Receive createReceive() {
        return receiveBuilder()
                .match(String.class, sku -> {
                    Thread.sleep(100);
                    getSender().tell(sku, getSelf());
                })
                .build();
    }
}
