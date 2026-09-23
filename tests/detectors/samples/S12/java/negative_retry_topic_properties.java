package com.example.retrytopic;

import java.util.ArrayList;
import java.util.List;

public class RetryTopicPropertiesFactory {
    private final int maxAttempts;
    private final int retryTopicsAmount;

    public RetryTopicPropertiesFactory(List<Long> backOffValues) {
        this.maxAttempts = backOffValues.size() + 1;
        this.retryTopicsAmount = backOffValues.size();
    }

    public List<String> topicSuffixes() {
        List<String> suffixes = new ArrayList<>();
        for (int backOffIndex = 0; backOffIndex < this.retryTopicsAmount; backOffIndex++) {
            suffixes.add("-retry-" + backOffIndex);
        }
        return suffixes;
    }
}
