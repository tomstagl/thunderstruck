export const albumTouch = `
  UPDATE album SET "updatedAt" = clock_timestamp()
  WHERE "id" IN (SELECT "albumId" FROM inserted_rows)
    AND NOT EXISTS (SELECT FROM inserted_rows WHERE role = 'owner');
`;
