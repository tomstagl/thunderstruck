package com.example.logs;

import com.rabbitmq.client.Channel;
import com.rabbitmq.client.DeliverCallback;

// A server-named queue is exclusive and auto-delete: it disappears with the
// consumer's connection, so acknowledging would save nothing after a crash.
// Direct reply-to requires autoAck=true.
public class LogTail {
    void start(Channel channel, DeliverCallback cb) throws Exception {
        String queueName = channel.queueDeclare().getQueue();
        channel.queueBind(queueName, "logs", "");
        channel.basicConsume(queueName, true, cb, tag -> { });
    }

    void exclusive(Channel channel, DeliverCallback cb) throws Exception {
        channel.queueDeclare("tail-1", false, true, true, null);
        channel.basicConsume("tail-1", true, cb, tag -> { });
    }

    void replies(Channel channel, DeliverCallback cb) throws Exception {
        channel.basicConsume("amq.rabbitmq.reply-to", true, cb, tag -> { });
    }
}
