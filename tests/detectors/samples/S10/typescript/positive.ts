import { withRetry } from "./retry";

export async function loadProfile(id: string) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const res = await withRetry(() => fetchProfile(id));
    if (res.ok) return res;
  }
  throw new Error("failed");
}
