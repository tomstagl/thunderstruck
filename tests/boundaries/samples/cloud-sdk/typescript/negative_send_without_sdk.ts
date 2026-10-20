export function notify(bus: Bus) {
  bus.send(new RefreshCommand());
}
