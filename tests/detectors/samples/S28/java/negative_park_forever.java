package com.example.launcher;

import java.util.concurrent.CountDownLatch;

// Parks the main thread until the process is killed. The latch is never
// counted down by design: waiting forever is the point.
public class Launcher {
    public static void main(String[] args) throws InterruptedException {
        startServices();
        System.out.println("Started, press Ctrl + C to stop");
        new CountDownLatch(1).await();
    }

    static void startServices() {
    }
}
