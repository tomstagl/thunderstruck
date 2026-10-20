import java.nio.file.Files;
import java.nio.file.Path;

class Config {
    String load(Path p) throws Exception {
        return Files.readString(p);  // boundary: filesystem
    }
}
