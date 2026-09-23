package com.example.workers;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

public class WorkerMetricsService {
    private final MongoTemplate mongoTemplate;
    private final WorkerRepository workerRepository;

    public WorkerMetricsService(MongoTemplate mongoTemplate, WorkerRepository workerRepository) {
        this.mongoTemplate = mongoTemplate;
        this.workerRepository = workerRepository;
    }

    public int busyCpus() {
        int busy = 0;
        List<Worker> workers = mongoTemplate.find(new Query(), Worker.class);
        for (final Worker worker : workers) {
            if (!worker.getComputingTaskIds().isEmpty()) {
                busy += worker.getComputingTaskIds().size();
            }
        }
        return busy;
    }
}
