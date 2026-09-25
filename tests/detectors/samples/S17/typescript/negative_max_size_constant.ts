const maxProtocolCacheSize = 100;
const protocolCache = new Map<string, string | false>();

export const setProtocolCache = (key: string, value: string | false): void => {
  if (!protocolCache.has(key) && protocolCache.size >= maxProtocolCacheSize) {
    protocolCache.delete(protocolCache.keys().next().value!);
  }
  protocolCache.set(key, value);
};
