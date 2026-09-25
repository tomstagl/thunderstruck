const COMPLETED_AUTH_TTL_MS = 30 * 1000;
const completedAuths = new Map<string, unknown>();

export function complete(state: string, result: unknown) {
  completedAuths.set(state, result);
  setTimeout(() => completedAuths.delete(state), COMPLETED_AUTH_TTL_MS);
}
