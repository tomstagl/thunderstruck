package com.example.inventory;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class StockLedger {
    private final HttpClient http = HttpClient.newHttpClient();
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition restocked = lock.newCondition();

    public synchronized void reserve(HttpRequest request) throws Exception {
        http.send(request, HttpResponse.BodyHandlers.ofString());
    }

    public void release(HttpRequest request) throws Exception {
        lock.lock();
        try {
            http.send(request, HttpResponse.BodyHandlers.ofString());
        } finally {
            lock.unlock();
        }
    }

    public void awaitStock() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            restocked.await();
        } finally {
            lock.unlock();
        }
    }
}
