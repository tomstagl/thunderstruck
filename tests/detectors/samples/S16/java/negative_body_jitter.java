package com.example.jobs;

import java.util.concurrent.ThreadLocalRandom;
import org.springframework.scheduling.annotation.Scheduled;

public class SyncJob {
    @Scheduled(cron = "0 0 * * * *")
    public void syncAll() throws InterruptedException {
        log("starting sync");
        countRun();
        Thread.sleep(ThreadLocalRandom.current().nextLong(30_000));
        run();
    }

    private void log(String message) { }

    private void countRun() { }

    private void run() { }
}
