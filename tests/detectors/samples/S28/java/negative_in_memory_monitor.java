package com.example.inventory;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.locks.ReentrantLock;

public class Counter {
    private final Map<String, Integer> counts = new HashMap<>();
    private final ReentrantLock lock = new ReentrantLock();

    public synchronized void increment(String key) {
        counts.merge(key, 1, Integer::sum);
    }

    public int read(String key) {
        lock.lock();
        try {
            return counts.getOrDefault(key, 0);
        } finally {
            lock.unlock();
        }
    }
}
