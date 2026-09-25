import * as fs from 'fs';
export function tryUnlink(p: string) {
  try { fs.unlinkSync(p); } catch (_ignored) {}
}
