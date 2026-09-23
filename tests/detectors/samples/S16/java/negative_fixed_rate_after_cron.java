package com.example.jobs;

import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;
import org.springframework.scheduling.annotation.Scheduled;

public class Jobs {
    @SchedulerLock(name = "hourly", lockAtMostFor = "PT10M")
    @Scheduled(cron = "0 0 * * * *")
    void hourly() { run(); }

    @Scheduled(fixedRate = 5000)
    void poll() { run(); }

    private void run() { }
}
