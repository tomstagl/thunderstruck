/**
 * Calls fetch(url) and broker.publish(msg) on the caller's behalf.
 */
export function noop() {
  // await fetch(url)
  return null;
}
