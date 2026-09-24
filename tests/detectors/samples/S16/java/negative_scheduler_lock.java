package com.example.jobs;

import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;
import org.springframework.scheduling.annotation.Scheduled;

public class SyncJob {
    @Scheduled(cron = "0 0 * * * *")
    @SchedulerLock(name = "syncAll", lockAtMostFor = "PT10M")
    public void syncAll() {
        run();
    }

    @SchedulerLock(name = "report", lockAtMostFor = "PT10M")
    @Scheduled(cron = "0 0 2 * * *")
    public void report() {
        run();
    }

    private void run() { }
}
