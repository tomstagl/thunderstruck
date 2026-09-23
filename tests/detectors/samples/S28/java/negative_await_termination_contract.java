package com.example.server;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

// awaitTermination() with no arguments is the untimed half of a server API
// whose timed variant, awaitTermination(timeout, unit), sits beside it. The
// caller who wants a bound calls that one.
public class ManagedServer {
    private final Object lock = new Object();
    private final CountDownLatch terminationLatch = new CountDownLatch(1);
    private boolean terminated;

    public boolean awaitTermination(long timeout, TimeUnit unit) throws InterruptedException {
        return terminationLatch.await(timeout, unit);
    }

    public void awaitTermination() throws InterruptedException {
        synchronized (lock) {
            while (!terminated) {
                lock.wait();
            }
        }
    }

    public void terminate() {
        synchronized (lock) {
            terminated = true;
            lock.notifyAll();
        }
        terminationLatch.countDown();
    }
}
