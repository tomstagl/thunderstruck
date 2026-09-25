// The provider rate limits per account; surface its budget to the caller.
export function rateLimitInfo(headers: Record<string, string>) {
  return {
    limit: Number.parseInt(headers['x-ratelimit-limit'], 10),
    remaining: Number.parseInt(headers['x-ratelimit-remaining'], 10),
  };
}
