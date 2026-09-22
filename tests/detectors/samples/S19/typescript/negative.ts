export function record(event: Event) {
  try {
    writeEvent(event);
  } catch (e) {
    log.error({ err: e }, "failed to write event");
    throw e;
  }
}
