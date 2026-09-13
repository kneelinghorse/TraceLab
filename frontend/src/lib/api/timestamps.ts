/** Legacy API datetimes omit the offset but are stored as UTC in PostgreSQL. */
export function parseApiTimestamp(value: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
}
