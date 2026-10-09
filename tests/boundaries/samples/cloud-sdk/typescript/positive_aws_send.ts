import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

export async function get(client: S3Client, key: string) {
  return client.send(new GetObjectCommand({ Bucket: "b", Key: key }));  // boundary: cloud SDK
}
