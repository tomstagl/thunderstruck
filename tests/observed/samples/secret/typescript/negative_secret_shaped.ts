import { SecretsManager } from "@aws-sdk/client-secrets-manager";

const sm = new SecretsManager({});

export async function token() {
  // await sm.getSecretValue({ SecretId: "prod/commented-out" });
  const out = await sm.getSecretValue({ SecretId: "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd" });
  return out.SecretString;
}
