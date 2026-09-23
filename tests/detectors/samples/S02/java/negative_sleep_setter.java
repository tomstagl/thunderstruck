package com.example.worker;

public class WorkerConfig {
    private int retries = 0;

    public void configure(Worker worker) {
        worker.setMaxSleepMs(60000);
        retries = 3;
    }

    interface Worker {
        void setMaxSleepMs(long ms);
    }
}
