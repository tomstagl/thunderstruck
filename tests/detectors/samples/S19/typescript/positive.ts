export function record(event: Event) {
  try {
    writeEvent(event);
  } catch (e) {
  }
}
