import { expect, it } from "vitest";
import { parseApiTimestamp } from "./timestamps";
it("interprets offset-free API values as UTC and preserves explicit offsets", () => {
  expect(parseApiTimestamp("2026-09-13T15:00:00").toISOString()).toBe("2026-09-13T15:00:00.000Z");
  expect(parseApiTimestamp("2026-09-13T15:00:00Z").toISOString()).toBe("2026-09-13T15:00:00.000Z");
  expect(parseApiTimestamp("2026-09-13T15:00:00-05:00").toISOString()).toBe("2026-09-13T20:00:00.000Z");
});
