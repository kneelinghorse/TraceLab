import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ReactNode } from "react";
import type { GraphNeighborhood, GraphNode } from "@/lib/api/graph";

const mocks = vi.hoisted(() => ({
  neighborhood: vi.fn(), search: vi.fn(),
  router: { isReady: true, query: {} as Record<string, string>, push: vi.fn() },
}));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "reader" } }) }));
vi.mock("@/lib/api/graph", async original => ({ ...await original<typeof import("@/lib/api/graph")>(), graphApi: { neighborhood: mocks.neighborhood } }));
vi.mock("@/lib/api/navigation", () => ({ navigationApi: { search: mocks.search } }));

import GraphPage from "@/pages/graph";
import { NeighborhoodDiagram } from "@/components/graph/NeighborhoodDiagram";
import { NeighborhoodList } from "@/components/graph/NeighborhoodList";
import { RelationshipLink } from "@/components/graph/RelationshipLink";
import { graphHref } from "@/lib/api/graph";
import { HttpError, httpClient } from "@/lib/api/http";

const types = ["project", "document", "mission", "report", "collection", "evidence"] as const;
const id = (index: number) => `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
function node(type: GraphNode["type"], index: number, title = `${type} title`): GraphNode {
  return { type, id: id(index), key: `${type}:${id(index)}`, title,
    href: `/${type === "evidence" ? "evidence" : type + "s"}/${id(index)}`,
    attributes: { updated_at: "2026-09-14T18:00:00+00:00" } };
}
const root = node("project", 1);
const document = node("document", 2, "A long document title that must remain fully available to readers of the relationship list");
const mission = node("mission", 3);
const evidence = node("evidence", 4);
const graph: GraphNeighborhood = {
  root, nodes: [root, document, mission, evidence],
  edges: [
    { from: root.key, to: document.key, relation: "documents", basis: "documents.project_id" },
    { from: root.key, to: mission.key, relation: "missions", basis: "missions.project_id" },
    { from: document.key, to: evidence.key, relation: "evidence", basis: "document_evidence_filter" },
    { from: mission.key, to: document.key, relation: "result_documents", basis: "missions.result_document_ids" },
  ],
  groups: [
    { from_key: root.key, relation: "documents", target_type: "document", shown: 1, total: 53 },
    { from_key: root.key, relation: "missions", target_type: "mission", shown: 1, total: 1 },
    { from_key: document.key, relation: "evidence", target_type: "evidence", shown: 1, total: 47 },
    { from_key: mission.key, relation: "result_documents", target_type: "document", shown: 1, total: 1 },
  ], truncated: true,
};

beforeEach(() => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  mocks.router.isReady = true;
  mocks.router.query = {};
  mocks.router.push.mockReset().mockResolvedValue(true);
  mocks.neighborhood.mockReset().mockResolvedValue(graph);
  mocks.search.mockReset().mockResolvedValue({ query: "research", groups: types.map((type, index) => ({
    entity_type: type, total: 31, page: 1, page_size: 5,
    items: [{ id: id(index + 1), title: `${type} result`, href: node(type, index + 1).href }],
  })) });
});
async function browser(component: ReactNode = <GraphPage />) {
  let view: ReturnType<typeof render>;
  await act(async () => { view = render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>{component}</SWRConfig>); });
  return view!;
}

describe("relationship accessibility and truthful totals", () => {
  it("gives the list every diagram node and every edge, including repeated targets", () => {
    const center = vi.fn();
    const view = render(<><NeighborhoodDiagram neighborhood={graph} /><NeighborhoodList neighborhood={graph} onCenter={center} /></>);
    const svg = screen.getByRole("img", { name: /Relationship diagram/ });
    const svgKeys = new Set([...svg.querySelectorAll("[data-graph-node-key]")].map(n => n.getAttribute("data-graph-node-key")));
    const rows = [...view.container.querySelectorAll("[data-list-node-key]")];
    expect(svgKeys).toEqual(new Set(graph.nodes.map(n => n.key)));
    expect(new Set(rows.map(row => row.getAttribute("data-list-node-key")))).toEqual(svgKeys);
    expect(svg.querySelectorAll("a,button,input,[tabindex]")).toHaveLength(0);
    for (const edge of graph.edges) {
      const row = view.container.querySelector(`[data-edge-key="${edge.from}>${edge.relation}>${edge.to}"]`)!;
      const target = graph.nodes.find(n => n.key === edge.to)!;
      expect(within(row as HTMLElement).getByRole("link", { name: target.title })).toHaveAttribute("href", target.href);
      fireEvent.click(within(row as HTMLElement).getByRole("button", { name: /Center here/ }));
      expect(center).toHaveBeenLastCalledWith(target);
    }
    expect(screen.getByText("1 of 53 shown")).toBeInTheDocument();
    expect(screen.getByText("1 of 47 shown")).toBeInTheDocument();
    expect(screen.getByText("Hop 2", { exact: true })).toBeInTheDocument();
    expect(within(svg).queryByText(document.title)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: document.title })).toHaveLength(2);
  });

  it.each(types)("provides the canonical %s detail entry link", type => {
    render(<RelationshipLink type={type} id={id(1)} />);
    expect(screen.getByRole("link", { name: "View relationships" })).toHaveAttribute("href", `/graph?root=${type}:${id(1)}`);
  });
});

describe("the relationship page", () => {
  it("finds roots across all six types without sending an unscoped neighborhood request", async () => {
    await browser();
    expect(mocks.neighborhood).not.toHaveBeenCalled();
    const input = screen.getByRole("textbox", { name: "Find an object" });
    fireEvent.change(input, { target: { value: "research" } });
    fireEvent.submit(input.closest("form")!);
    await screen.findByRole("button", { name: "Center on evidence result" });
    expect(mocks.search).toHaveBeenCalledWith("research");
    for (const [index, type] of types.entries()) {
      fireEvent.click(screen.getByRole("button", { name: `Center on ${type} result` }));
      expect(mocks.router.push).toHaveBeenLastCalledWith(graphHref(type, id(index + 1), 1), undefined, { shallow: true });
    }
  });

  it.each([1, 2] as const)("loads depth %s from the URL and pushes root/depth changes into history", async depth => {
    mocks.router.query = { root: root.key, depth: String(depth) };
    await browser();
    await screen.findByRole("img", { name: /Relationship diagram/ });
    expect(mocks.neighborhood).toHaveBeenCalledWith("project", root.id, depth);
    const list = screen.getByRole("region", { name: "Relationship list" });
    fireEvent.click(within(list).getByRole("button", { name: `Center here: ${mission.title}` }));
    expect(mocks.router.push).toHaveBeenLastCalledWith(graphHref("mission", mission.id, depth), undefined, { shallow: true });
    fireEvent.click(screen.getByRole("button", { name: depth === 1 ? "Depth 2" : "Depth 1", exact: true }));
    expect(mocks.router.push).toHaveBeenLastCalledWith(graphHref("project", root.id, depth === 1 ? 2 : 1), undefined, { shallow: true });
  });

  it.each([[403, "Access to this object is restricted"], [404, "Root object not found"], [500, "Relationships could not load"]])("distinguishes HTTP %s", async (status, title) => {
    mocks.router.query = { root: root.key };
    mocks.neighborhood.mockRejectedValue(new HttpError("private server detail", Number(status)));
    await browser();
    expect(await screen.findByText(String(title))).toBeInTheDocument();
    expect(screen.queryByText("private server detail")).not.toBeInTheDocument();
    if (status === 500) {
      mocks.neighborhood.mockResolvedValue(graph);
      fireEvent.click(screen.getByRole("button", { name: "Retry", exact: true }));
      await screen.findByRole("img", { name: /Relationship diagram/ });
    }
  });

  it("separates loading, an isolated root and an invalid root link", async () => {
    mocks.router.query = { root: root.key };
    let resolve!: (value: GraphNeighborhood) => void;
    mocks.neighborhood.mockImplementation(() => new Promise<GraphNeighborhood>(done => { resolve = done; }));
    const view = await browser();
    expect(screen.getByText("Loading relationships…")).toBeInTheDocument();
    await act(async () => resolve({ root, nodes: [root], edges: [], groups: [], truncated: false }));
    expect(await screen.findByText("No accessible relationships are recorded")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: root.title })).toHaveAttribute("href", root.href);
    view.unmount();
    mocks.router.query = { root: "project:not-a-uuid" };
    mocks.neighborhood.mockClear();
    await browser();
    expect(screen.getByText("Invalid relationship link")).toBeInTheDocument();
    expect(mocks.neighborhood).not.toHaveBeenCalled();
  });

  it("reports root-search failure with retry and its own empty state", async () => {
    mocks.search.mockRejectedValue(new Error("search unavailable"));
    await browser();
    const input = screen.getByRole("textbox", { name: "Find an object" });
    fireEvent.change(input, { target: { value: "missing" } });
    fireEvent.submit(input.closest("form")!);
    await screen.findByText("Objects could not load");
    mocks.search.mockResolvedValue({ query: "missing", groups: [] });
    fireEvent.click(screen.getByRole("button", { name: "Retry", exact: true }));
    await screen.findByText("No matching objects");
  });

  it("uses the mounted REST verb and explicit bounded parameters", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api/graph")>("@/lib/api/graph");
    const get = vi.spyOn(httpClient, "get").mockResolvedValue(graph);
    try {
      await actual.graphApi.neighborhood("document", document.id, 2);
      expect(get).toHaveBeenCalledWith("/graph/neighborhood", { params: { root_type: "document", root_id: document.id, depth: 2, per_relation_limit: 12, max_nodes: 60 } });
    } finally { get.mockRestore(); }
  });
});
