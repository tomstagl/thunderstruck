export function toError(res: Response): Error | null {
  if (res.status === 429) return new RateLimitedError(res);
  if (res.status >= 500) return new UpstreamError(res);
  return null;
}
