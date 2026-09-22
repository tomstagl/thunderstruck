import { withRetry } from "./retry";

export async function loadProfile(id: string) {
  return withRetry(() => fetchProfile(id));
}
