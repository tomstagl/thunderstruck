package com.example.pool;

import java.util.concurrent.BlockingDeque;
import java.util.concurrent.LinkedBlockingDeque;

public class ConnectionPool<T> {
    private final BlockingDeque<T> idleObjects = new LinkedBlockingDeque<>();

    public T borrow() {
        return idleObjects.pollFirst();
    }

    public void giveBack(T obj) {
        idleObjects.offerFirst(obj);
    }
}
