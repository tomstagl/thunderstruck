package com.example.producer;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

// A send that may have failed synchronously: get() runs only once isDone()
// says the future has completed, so it returns at once.
public class RecordSender {
    private final Producer producer;

    public RecordSender(Producer producer) {
        this.producer = producer;
    }

    public CompletableFuture<Long> send(String record) {
        CompletableFuture<Long> result = new CompletableFuture<>();
        Future<Long> sendFuture = producer.send(record, result::complete);
        if (sendFuture.isDone()) {
            try {
                sendFuture.get();
            }
            catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", e);
            }
            catch (ExecutionException e) {
                result.completeExceptionally(e.getCause());
            }
        }
        return result;
    }

    interface Producer {
        Future<Long> send(String record, java.util.function.Consumer<Long> callback);
    }
}
