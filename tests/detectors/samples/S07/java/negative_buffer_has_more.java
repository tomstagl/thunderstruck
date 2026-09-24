package com.example.io;

import java.io.IOException;
import java.net.SocketTimeoutException;

// A read loop that asks a stream buffer whether bytes remain (jsoup's
// ControllableInputStream.checkTruncated). `hasMore()` on a buffer is not a
// more-pages flag.
public class CappedInputStream {
    private final ReadBuffer buff;
    private boolean truncated;
    private int remaining;

    public CappedInputStream(ReadBuffer buff) {
        this.buff = buff;
    }

    public boolean checkTruncated() throws IOException {
        while (!truncated && remaining <= 0) {
            try {
                truncated = buff.hasMore();
                break;
            } catch (SocketTimeoutException e) {
                throw e;
            }
        }
        return truncated;
    }
}

interface ReadBuffer {
    boolean hasMore() throws IOException;
}
