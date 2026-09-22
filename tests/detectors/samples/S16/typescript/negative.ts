const jitter = Math.random() * 30_000;
setTimeout(() => {
  setInterval(() => {
    void runSync();
  }, 60_000);
}, jitter);
