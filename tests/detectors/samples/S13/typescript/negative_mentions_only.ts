import { ChildPool } from './child-pool';
export * from './child-pool';

export interface PgModule {
  Pool: new (config?: string) => PgPool;
}

export const hint = 'Pass an already-constructed `pg.Pool` instance instead.';
export const skipped = ['tests/child-pool.test.ts'];
