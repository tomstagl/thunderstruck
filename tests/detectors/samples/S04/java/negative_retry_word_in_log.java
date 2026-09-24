package com.example.listener;

import java.util.List;

// The catch-alls log and move on. "retry" appears only inside log messages;
// nothing here retries the failed call.
public class RecoveryTracker {
    private final Logger logger = new Logger();

    public void recover(List<String> remaining, Exception thrown) {
        if (!remaining.isEmpty()) {
            try {
                if (recovered(remaining.get(0), thrown)) {
                    remaining.remove(0);
                }
            }
            catch (Exception e) {
                logger.debug(remaining.get(0) + " included in remaining due to retry back off " + thrown);
            }
        }
    }

    public void runLoop() {
        while (running()) {
            try {
                handleAsyncFailure();
            }
            catch (Exception e) {
                logger.debug("Failed to process async retry messages. skip this time, try it again next loop.");
            }
            pollAndInvoke();
        }
    }

    private boolean recovered(String record, Exception thrown) { return true; }
    private boolean running() { return false; }
    private void handleAsyncFailure() { }
    private void pollAndInvoke() { }

    static class Logger {
        void debug(String message) { }
    }
}
