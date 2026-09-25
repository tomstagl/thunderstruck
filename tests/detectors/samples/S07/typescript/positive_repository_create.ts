export class ImportJob {
  constructor(private assetRepository: AssetRepository) {}

  async handle(rows: Row[]) {
    for (const row of rows) {
      await this.assetRepository.create(row);
    }
  }
}
