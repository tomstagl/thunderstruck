package com.example.inventory;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class StockLedger {
    private final HttpClient http = HttpClient.newHttpClient();
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition restocked = lock.newCondition();

    public void release(HttpRequest request) throws Exception {
        if (lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            try {
                http.send(request, HttpResponse.BodyHandlers.ofString());
            } finally {
                lock.unlock();
            }
        }
    }

    public boolean awaitStock() throws InterruptedException {
        if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false;
        }
        try {
            return restocked.await(500, TimeUnit.MILLISECONDS);
        } finally {
            lock.unlock();
        }
    }
}
