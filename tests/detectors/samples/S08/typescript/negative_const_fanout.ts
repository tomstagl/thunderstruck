const REGIONS = ['eu', 'us', 'ap'] as const;
export async function healthAll() {
  return Promise.all(REGIONS.map((r) => ping(r)));
}
