package com.example.detector;

import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Scheduled;

public class WorkerLostDetector {
    @Scheduled(fixedRate = 5000)
    public void pollLatestBlock() {
        run();
    }

    @Scheduled(fixedRateString = "#{@cronConfiguration.getWorkerLost()}")
    public void detect() {
        run();
    }

    @Scheduled(
            fixedRateString = "${logs.purge-rate-in-days}",
            timeUnit = TimeUnit.DAYS)
    void purgeLogs() {
        run();
    }

    private void run() { }
}
