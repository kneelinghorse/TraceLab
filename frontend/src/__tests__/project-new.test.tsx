import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NewProjectPage from "@/pages/projects/new";

const mocks = vi.hoisted(() => ({
  createProject: vi.fn(),
  listSpaces: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { createProject: mocks.createProject } }));
vi.mock("@/lib/api/spaces", () => ({ spacesApi: { list: mocks.listSpaces } }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "self" } }),
}));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("next/router", () => ({ useRouter: () => ({ query: {}, push: mocks.push, pathname: "/projects/new" }) }));

const MINE = { id: "space-mine", name: "Syndy's Space", created_at: "", personal_owner_id: "self" };
const PARTS = { id: "space-parts", name: "Parts Town", created_at: "", personal_owner_id: null };

function page() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>
      <NewProjectPage />
    </SWRConfig>,
  );
}

function submit(name: string) {
  fireEvent.change(screen.getByLabelText("Project name"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "Create project" }));
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.createProject.mockResolvedValue({ id: "p-1", name: "Created" });
  mocks.push.mockResolvedValue(true);
});

// PERSONAL-2 (decision #533): a member picks where a new project lives only when there is a choice.
describe("New project page", () => {
  it("shows no Space picker with one Space and sends no workspace_id", async () => {
    mocks.listSpaces.mockResolvedValue([MINE]);
    page();
    await waitFor(() => expect(mocks.listSpaces).toHaveBeenCalled());
    expect(screen.queryByRole("combobox", { name: "Space" })).toBeNull();
    submit("Field notes");
    await waitFor(() => expect(mocks.createProject).toHaveBeenCalledTimes(1));
    expect(mocks.createProject.mock.calls[0][0]).not.toHaveProperty("workspace_id");
  });

  it("defaults to My Space, which leaves the placement to the server", async () => {
    mocks.listSpaces.mockResolvedValue([MINE, PARTS]);
    page();
    const picker = (await screen.findByRole("combobox", { name: "Space" })) as HTMLSelectElement;
    expect(picker.value).toBe("");
    expect(within(picker).getAllByRole("option").map((option) => option.textContent)).toEqual(["My Space", "Parts Town"]);
    submit("Field notes");
    await waitFor(() => expect(mocks.createProject).toHaveBeenCalledTimes(1));
    expect(mocks.createProject.mock.calls[0][0]).not.toHaveProperty("workspace_id");
  });

  it("creates in the shared Space the member picks", async () => {
    mocks.listSpaces.mockResolvedValue([MINE, PARTS]);
    page();
    fireEvent.change(await screen.findByRole("combobox", { name: "Space" }), { target: { value: "space-parts" } });
    submit("Catalog audit");
    await waitFor(() =>
      expect(mocks.createProject).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Catalog audit", workspace_id: "space-parts" }),
      ),
    );
    expect(mocks.push).toHaveBeenCalledWith("/projects/p-1");
  });
});
