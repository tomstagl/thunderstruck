package com.example.client;

import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class ProfileLoader {
    public String load() {
        CompletableFuture<String> future = CompletableFuture.supplyAsync(this::fetch)
                .orTimeout(5, TimeUnit.SECONDS);
        return future.join();
    }

    public CompletableFuture<String> cached(Optional<String> hit) {
        return CompletableFuture.completedFuture(hit.get());
    }

    private String fetch() { return "profile"; }
}
