package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;

public class SyncJob {
    @Scheduled(fixedRateString = "PT1H",
               initialDelayString = "#{T(java.util.concurrent.ThreadLocalRandom).current().nextInt(60000)}")
    public void syncAll() {
        run();
    }

    private void run() { }
}
