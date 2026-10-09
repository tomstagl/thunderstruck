export function start(poll: () => void) {
  return setInterval(poll, 60_000);  // boundary: scheduler
}
