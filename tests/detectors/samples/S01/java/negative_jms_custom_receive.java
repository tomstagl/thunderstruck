package com.example.mail;

import javax.jms.Session;

// A JMS import in the file does not make every receive() a JMS receive().
// Inbox is the application's own type.
public class Mailbox {
    private final Inbox inbox = new Inbox();

    public String next() {
        return inbox.receive();
    }

    public void read(java.net.DatagramSocket socket, java.net.DatagramPacket packet, javax.jms.MessageConsumer consumer) throws Exception {
        socket.receive(packet);
        consumer.receiveNoWait();
    }
}

class Inbox {
    String receive() {
        return "";
    }
}
