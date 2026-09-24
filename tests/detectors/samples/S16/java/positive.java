package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;

public class SyncJob {
    @Scheduled(cron = "0 0 * * * *")
    public void syncAll() {
        run();
    }

    private void run() { }
}
