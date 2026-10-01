import { describe, expect, it, vi } from "vitest";
import { handleSmokeApiRequest } from "./ui-shell-transport.mjs";

describe.each([false, true])("read-only smoke, directProduction=%s", directProduction => {
  function setup(method: string, pathname: string, origin?: string) {
    const api = "https://api.tracelab.aquex.ai";
    const base = directProduction ? "https://tracelab.aquex.ai" : "http://localhost:3100";
    const route = {
      request: () => ({ url: () => (origin ?? (directProduction ? api : "http://localhost:8000")) + pathname,
        method: () => method, headers: () => ({ authorization: "Bearer placeholder" }), postData: () => '{"query":"fixture"}' }),
      fulfill: vi.fn().mockResolvedValue(undefined), continue: vi.fn().mockResolvedValue(undefined), abort: vi.fn().mockResolvedValue(undefined),
    };
    const transportErrors: unknown[] = [], suppressedWrites: unknown[] = [];
    const fetchResponse = vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => "{}" });
    const handle = (request: typeof route) => handleSmokeApiRequest(request, { api, base, directProduction, apiKey: "test-key", transportErrors, suppressedWrites, fetchResponse });
    return { route, handle, transportErrors, suppressedWrites, fetchResponse, base };
  }

  it.each(["/api/v1/activity/viewed", "/api/v1/activity/viewed/evidence"])("fulfills %s locally without forwarding a write", async path => {
    const t = setup("PUT", path);
    await t.handle(t.route);
    expect(t.route.fulfill).toHaveBeenCalledWith(expect.objectContaining({status: 200, json: {viewed: 0, new_total: 0}, headers: expect.objectContaining({"access-control-allow-origin": t.base})}));
    expect(t.suppressedWrites).toEqual([{method: "PUT", path}]);
    expect(t.fetchResponse).not.toHaveBeenCalled();
    expect(t.route.continue).not.toHaveBeenCalled();
    expect(t.route.abort).not.toHaveBeenCalled();
    expect(t.transportErrors).toEqual([]);
  });

  it.each([
    ["POST", "/api/v1/missions"], ["PUT", "/api/v1/projects/project-1"],
    ["PATCH", "/api/v1/activity/viewed/evidence"], ["DELETE", "/api/v1/documents/doc-1"],
    ["POST", "/api/v1/activity/viewed/evidence"], ["PUT", "/api/v1/activity/viewed/evidence/extra"],
    ["PUT", "/api/v1/activity/viewed/evidence/"],
  ])("rejects %s %s before any production transport", async (method, path) => {
    const t = setup(method, path);
    await t.handle(t.route);
    expect(t.route.abort).toHaveBeenCalledOnce();
    expect(t.transportErrors).toHaveLength(1);
    expect(t.fetchResponse).not.toHaveBeenCalled();
    expect(t.route.continue).not.toHaveBeenCalled();
    expect(t.route.fulfill).not.toHaveBeenCalled();
    expect(t.suppressedWrites).toEqual([]);
  });

  it.each([["GET", "/api/v1/evidence"], ["POST", "/api/v1/pedr/search"]])("retains the existing %s read", async (method, path) => {
    const t = setup(method, path);
    await t.handle(t.route);
    expect(t.transportErrors).toEqual([]);
    expect(t.route.abort).not.toHaveBeenCalled();
    if (directProduction) {
      expect(t.route.continue).toHaveBeenCalledWith({headers: {"x-api-key": "test-key"}});
      expect(t.fetchResponse).not.toHaveBeenCalled();
    } else {
      expect(t.fetchResponse).toHaveBeenCalledWith("https://api.tracelab.aquex.ai" + path, expect.objectContaining({method}));
      expect(t.route.continue).not.toHaveBeenCalled();
    }
  });
});
