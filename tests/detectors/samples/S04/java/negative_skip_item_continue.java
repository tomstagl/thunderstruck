package com.example.importer;

import java.io.File;
import java.util.List;
import java.util.logging.Logger;

public class Importer {
    private static final Logger log = Logger.getLogger("importer");

    public void importAll(List<File> files) {
        for (File f : files) {
            try {
                parse(f);
            } catch (Exception e) {
                log.warning("skipping bad file " + f + ": " + e);
                continue;
            }
            index(f);
        }
    }

    private void parse(File f) throws Exception { }
    private void index(File f) { }
}
