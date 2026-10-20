import org.springframework.scheduling.annotation.Scheduled;

class Cleanup {
    @Scheduled(fixedRate = 60000)  // boundary: scheduler
    void run() {
        purge();
    }
}
