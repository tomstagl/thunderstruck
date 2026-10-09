import { readFile } from "node:fs/promises";

export async function load(path: string) {
  return JSON.parse(await readFile(path, "utf8"));  // boundary: filesystem
}
