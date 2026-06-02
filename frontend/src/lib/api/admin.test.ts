import { beforeEach, describe, expect, it, vi } from "vitest";

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/lib/api/http", () => ({ httpClient: http }));

import { adminSpacesApi, adminUsersApi } from "@/lib/api/admin";

beforeEach(() => {
  http.get.mockReset().mockResolvedValue([]);
  http.post.mockReset().mockResolvedValue({});
  http.patch.mockReset().mockResolvedValue({});
  http.delete.mockReset().mockResolvedValue({});
});

// Pins the exact verb/path/body the client puts on the wire — the page tests
// mock this whole module, so a body-key or verb regression would otherwise pass.
describe("adminUsersApi HTTP contract", () => {
  it("list → GET /admin/users", async () => {
    await adminUsersApi.list();
    expect(http.get).toHaveBeenCalledWith("/admin/users");
  });

  it("create → POST /admin/users with the payload", async () => {
    const payload = {
      email: "a@x.com",
      password: "password123",
      display_name: "A",
      role: "member" as const,
    };
    await adminUsersApi.create(payload);
    expect(http.post).toHaveBeenCalledWith("/admin/users", payload);
  });

  it("setRole → PATCH /admin/users/{id}/role with { role }", async () => {
    await adminUsersApi.setRole("u1", "admin");
    expect(http.patch).toHaveBeenCalledWith("/admin/users/u1/role", { role: "admin" });
  });

  it("setActive → PATCH /admin/users/{id}/active with { is_active }", async () => {
    await adminUsersApi.setActive("u1", false);
    expect(http.patch).toHaveBeenCalledWith("/admin/users/u1/active", { is_active: false });
  });

  it("remove → DELETE /admin/users/{id}", async () => {
    await adminUsersApi.remove("u1");
    expect(http.delete).toHaveBeenCalledWith("/admin/users/u1");
  });
});

describe("adminSpacesApi HTTP contract", () => {
  it("list → GET /admin/spaces", async () => {
    await adminSpacesApi.list();
    expect(http.get).toHaveBeenCalledWith("/admin/spaces");
  });

  it("create → POST /admin/spaces with { name }", async () => {
    await adminSpacesApi.create("Research");
    expect(http.post).toHaveBeenCalledWith("/admin/spaces", { name: "Research" });
  });

  it("listMembers → GET /admin/spaces/{id}/members", async () => {
    await adminSpacesApi.listMembers("s1");
    expect(http.get).toHaveBeenCalledWith("/admin/spaces/s1/members");
  });

  it("addMember → POST /admin/spaces/{id}/members with { user_id }", async () => {
    await adminSpacesApi.addMember("s1", "u1");
    expect(http.post).toHaveBeenCalledWith("/admin/spaces/s1/members", { user_id: "u1" });
  });

  it("removeMember → DELETE /admin/spaces/{id}/members/{userId}", async () => {
    await adminSpacesApi.removeMember("s1", "u1");
    expect(http.delete).toHaveBeenCalledWith("/admin/spaces/s1/members/u1");
  });

  it("assignProjectSpace → PATCH /admin/projects/{id}/space (NOT /admin/spaces) with { space_id }", async () => {
    await adminSpacesApi.assignProjectSpace("p1", "s1");
    expect(http.patch).toHaveBeenCalledWith("/admin/projects/p1/space", { space_id: "s1" });
  });

  it("assignProjectSpace(null) → PATCH with { space_id: null } to un-assign", async () => {
    await adminSpacesApi.assignProjectSpace("p1", null);
    expect(http.patch).toHaveBeenCalledWith("/admin/projects/p1/space", { space_id: null });
  });
});
