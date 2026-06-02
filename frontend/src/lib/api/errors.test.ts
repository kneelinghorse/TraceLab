import { describe, expect, it } from "vitest";

import { apiErrorMessage } from "@/lib/api/errors";

describe("apiErrorMessage", () => {
  it("extracts a string detail (FastAPI HTTPException)", () => {
    expect(apiErrorMessage(new Error('{"detail":"Email already registered"}'))).toBe(
      "Email already registered",
    );
  });

  it("joins the msgs of a 422 validation-error array", () => {
    const err = new Error(
      '{"detail":[{"loc":["body","display_name"],"msg":"display_name cannot be blank","type":"value_error"},{"msg":"password too short"}]}',
    );
    expect(apiErrorMessage(err)).toBe("display_name cannot be blank; password too short");
  });

  it("returns the raw message when it is not JSON", () => {
    expect(apiErrorMessage(new Error("Network request failed"))).toBe("Network request failed");
  });

  it("uses the fallback for a non-Error value", () => {
    expect(apiErrorMessage("boom", "fallback msg")).toBe("fallback msg");
    expect(apiErrorMessage(undefined)).toBe("Something went wrong");
  });
});
