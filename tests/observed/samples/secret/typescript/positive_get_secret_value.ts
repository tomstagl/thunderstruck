import { SecretsManager } from "@aws-sdk/client-secrets-manager";

const sm = new SecretsManager({});

export async function token() {
  const out = await sm.getSecretValue({ SecretId: "prod/payments-api" });
  return out.SecretString;
}
