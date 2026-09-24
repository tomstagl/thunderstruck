package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;

public class Poller {
    @Scheduled(fixedDelay = 60000)
    public void poll() {
        run();
    }

    @Scheduled(fixedDelayString = "${poll.delay}", initialDelay = 1000)
    public void pollAgain() {
        run();
    }

    private void run() { }
}
