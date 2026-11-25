import { S3Client } from "@aws-sdk/client-s3";

const { LOG_LEVEL, S3_URL, AUTH_URL, X_URL, Y_ADDR } = process.env;

export const level = LOG_LEVEL;
export const s3 = new S3Client({ endpoint: S3_URL });
export const X = X_URL;

const cfg: { auth?: string } = {};
cfg.auth = AUTH_URL;

export async function second() {
  const b = S3_URL + "/v1";
  await fetch(b);
  await fetch(cfg.auth);
  return new FooClient(Y_ADDR);
}

export async function direct() {
  return fetch(process.env.AUTH_SERVER);
}
