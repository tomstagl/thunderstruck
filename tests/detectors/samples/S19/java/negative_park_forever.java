package com.example.launcher;

import java.util.concurrent.CountDownLatch;

// A launcher that starts background services and then parks its main thread
// until the process is killed. The latch is never counted down, so an
// interrupt is the only way out: swallowing it is how the wait ends, and
// nothing is lost.
public class Launcher {
    public static void main(String[] args) {
        startServices();
        System.out.println("Started, press Ctrl + C to stop");
        try {
            new CountDownLatch(1).await();
        } catch (InterruptedException e) {}
    }

    static void runUntilKilled() {
        startServices();
        try { Thread.currentThread().join(); } catch (InterruptedException e) { }
    }

    static void startServices() {
    }
}
