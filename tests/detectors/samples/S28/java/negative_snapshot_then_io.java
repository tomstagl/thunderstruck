package com.example.inventory;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.locks.ReentrantLock;

public class Flusher {
    private final HttpClient http = HttpClient.newHttpClient();
    private final ReentrantLock lock = new ReentrantLock();
    private final List<String> pending = new ArrayList<>();
    private int count;

    public synchronized int size() {
        return count;
    }

    public void flush(HttpRequest request) throws Exception {
        List<String> batch;
        synchronized (this) { batch = new ArrayList<>(pending); pending.clear(); }
        http.send(request, HttpResponse.BodyHandlers.ofString());
    }

    public void flushLocked(HttpRequest request) throws Exception {
        List<String> batch;
        lock.lock();
        try {
            batch = new ArrayList<>(pending);
        } finally {
            lock.unlock();
        }
        http.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
