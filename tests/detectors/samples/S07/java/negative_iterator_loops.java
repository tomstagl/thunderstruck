package com.example.parsing;

import java.util.Enumeration;
import java.util.Iterator;
import java.util.List;
import java.util.Properties;

// Iterator and Enumeration walks, and a byte-offset parser: loops that mention
// hasNext/hasMore/offset but never walk pages of a remote source.
public class FrameReader {
    public int countOpen(List<String> pages) {
        int open = 0;
        Iterator<String> it = pages.iterator();
        while (it.hasNext()) {
            String page = it.next();
            if (page.isEmpty()) {
                it.remove();
            }
            open++;
        }
        return open;
    }

    public void dump(Properties props) {
        Enumeration<?> names = props.propertyNames();
        while (names.hasMoreElements()) {
            System.out.println(names.nextElement());
        }
    }

    public int frames(byte[] buf) {
        int offset = 0;
        int frames = 0;
        while (offset < buf.length) {
            int len = buf[offset] & 0xff;
            offset += len + 1;
            frames++;
        }
        return frames;
    }
}
