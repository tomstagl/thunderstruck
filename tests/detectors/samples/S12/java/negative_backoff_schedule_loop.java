package com.example.backoff;

import java.util.ArrayList;
import java.util.List;

public class BackOffSchedule {
    private final int maxRetries;
    private final long initialInterval;
    private final double multiplier;

    public BackOffSchedule(int maxRetries, long initialInterval, double multiplier) {
        this.maxRetries = maxRetries;
        this.initialInterval = initialInterval;
        this.multiplier = multiplier;
    }

    public List<Long> intervals() {
        List<Long> out = new ArrayList<>();
        long interval = this.initialInterval;
        for (int i = 1; i < this.maxRetries; i++) {
            out.add(interval);
            interval = (long) (interval * this.multiplier);
        }
        return out;
    }
}
