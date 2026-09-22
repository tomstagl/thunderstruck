export async function save(payload: unknown) {
  let retries = 0;
  while (retries < 3) {
    const res = await post("/save", payload);
    if (res.status < 500 && res.status !== 429) return res;
    retries += 1;
  }
  throw new Error("failed");
}
