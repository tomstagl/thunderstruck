package com.example.audit;

import com.rabbitmq.client.Channel;
import com.rabbitmq.client.Consumer;

// basicQos is ignored for an autoAck consumer, so a missing prefetch is not
// this consumer's gap (S07 reports the autoAck itself).
public class AuditTail {
    void start(Channel channel, Consumer consumer) throws Exception {
        channel.basicConsume("audit", true, consumer);
    }
}
