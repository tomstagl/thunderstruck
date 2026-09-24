package com.example.service;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.retry.annotation.Retryable;

public class ReplicaService {
    private final ReplicaRepository repository;

    public ReplicaService(ReplicaRepository repository) {
        this.repository = repository;
    }

    @Retryable(retryFor = OptimisticLockingFailureException.class, maxAttempts = 5)
    public void markCompleted(String id) {
        Replica replica = repository.findById(id).orElseThrow();
        replica.setStatus("COMPLETED");
        repository.save(replica);
    }
}
