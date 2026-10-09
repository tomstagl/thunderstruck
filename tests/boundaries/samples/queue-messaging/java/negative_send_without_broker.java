class Mailer {
    void notify(Message m) {
        outbox.send(m);
    }
}
