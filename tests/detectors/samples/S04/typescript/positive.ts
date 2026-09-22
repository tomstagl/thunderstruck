export async function save(payload: unknown) {
  let retries = 0;
  while (retries < 3) {
    try {
      return await post("/save", payload);
    } catch (e) {
      retries += 1;
    }
  }
  throw new Error("failed");
}
