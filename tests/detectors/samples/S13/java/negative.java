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

class InventoryActor extends akka.actor.AbstractActor {
    static akka.actor.Props props() {
        return akka.actor.Props.create(InventoryActor.class).withDispatcher("blocking-io-dispatcher");
    }

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
