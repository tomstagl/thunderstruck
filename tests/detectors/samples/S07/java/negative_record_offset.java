package com.example.consumer;

import java.time.Duration;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;

// Loops that read a Kafka record's offset (into a local, or a log message)
// and a parser loop with a `skip` flag. Neither walks pages of a remote source.
public class RecordAuditor {
    private final ShareConsumer consumer;

    public RecordAuditor(ShareConsumer consumer) {
        this.consumer = consumer;
    }

    public void audit() {
        while (consumer.isRunning()) {
            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(100));
            for (ConsumerRecord<String, String> e : records) {
                long offset = e.offset();
                System.out.printf("partition=%d, offset=%d%n", e.partition(), offset);
                consumer.accept(e);
            }
        }
    }

    public int reconstruct(Object[] entries) {
        int pos = entries.length - 1;
        boolean skip = false;
        while (true) {
            if (pos == 0) {
                skip = true;
                break;
            }
            pos--;
        }
        return skip ? -1 : pos;
    }
}

interface ShareConsumer {
    boolean isRunning();
    ConsumerRecords<String, String> poll(Duration timeout);
    void accept(ConsumerRecord<String, String> record);
}
