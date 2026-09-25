export class DuplicateService {
  private mergeResult(assets: Asset[], albumsByAsset: Map<string, string[]> = new Map()) {
    return assets.map((asset) => albumsByAsset.get(asset.id) ?? []);
  }
}
