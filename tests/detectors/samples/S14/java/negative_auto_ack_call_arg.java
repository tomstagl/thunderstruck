package com.example.audit;

import com.rabbitmq.client.Channel;
import com.rabbitmq.client.DeliverCallback;

// An autoAck consumer whose queue name comes from a call: still autoAck, so
// prefetch does not apply.
public class AuditTail {
    void start(Channel channel, QueueProps props, DeliverCallback cb) throws Exception {
        channel.basicConsume(props.getQueue(), true, cb, tag -> { });
    }
}

interface QueueProps {
    String getQueue();
}
