// Requests, but never reads what comes back.
export function ping() {
  fetch("https://ledger.internal/v1/ping");
}
