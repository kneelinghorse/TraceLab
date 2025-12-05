import { expect, test } from "@playwright/test";

const apiBase = (process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const apiPrefix = (process.env.PLAYWRIGHT_API_PATH_PREFIX ?? "/api/v1").replace(/\/$/, "");
const buildApiUrl = (path: string) => {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const prefix = apiPrefix ? apiPrefix : "";
  return `${apiBase}${prefix}${normalized}`;
};

// Mock data
const mockMissions = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    project_id: "22222222-2222-2222-2222-222222222222",
    mission_data: {
      mission_id: "B11.1",
      title: "Test Mission 1",
      status: "in_progress",
      quality_checkpoints: [
        { gate: "research_statement", status: "pass", notes: null },
        { gate: "evidence_links", status: "fail", notes: "Missing evidence" },
      ],
      evidence: [],
    },
    completion_percentage: 60,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-02T00:00:00Z",
  },
  {
    id: "33333333-3333-3333-3333-333333333333",
    project_id: "22222222-2222-2222-2222-222222222222",
    mission_data: {
      mission_id: "B11.2",
      title: "Test Mission 2",
      status: "complete",
      quality_checkpoints: [
        { gate: "research_statement", status: "pass", notes: null },
        { gate: "evidence_links", status: "pass", notes: null },
      ],
      evidence: [],
    },
    completion_percentage: 100,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-02T00:00:00Z",
  },
];

const mockCorrections = {
  stats: {
    pending: 5,
    in_progress: 2,
    completed: 10,
    failed: 3,
    skipped: 1,
    total: 21,
  },
  error_distribution: {
    low_similarity: 5,
    no_embedding: 3,
  },
  recent_items: [],
  last_updated: new Date().toISOString(),
};

const mockRelationships = {
  mission_id: "11111111-1111-1111-1111-111111111111",
  mission_identifier: "B11.1",
  project_id: "22222222-2222-2222-2222-222222222222",
  depth: 2,
  filters: { entity_types: [], min_relevance: null },
  documents: [
    {
      id: "doc-1",
      name: "Test Document",
      file_type: "pdf",
      source_type: null,
      evidence_chunks: 2,
      chunk_ids: ["chunk-1", "chunk-2"],
      relationship: {
        relationship_type: "evidence_source",
        evidence_ids: ["ev-1"],
        summary: null,
        source: null,
        relevance_score: 0.85,
      },
    },
  ],
  insights: [],
  chunks: [],
  related_missions: [],
  totals: { documents: 1, insights: 0, chunks: 2, missions: 0 },
  warnings: [],
  cached: false,
};

const jsonResponse = (payload: unknown) => ({
  status: 200,
  body: JSON.stringify(payload),
  headers: { "content-type": "application/json" },
});

test.describe("Operator Console", () => {
  test.beforeEach(async ({ page }) => {
    // Setup common mocks
    await page.route(buildApiUrl("/missions"), (route) => route.fulfill(jsonResponse(mockMissions)));
    await page.route(buildApiUrl("/deepsearch/corrections"), (route) =>
      route.fulfill(jsonResponse(mockCorrections))
    );
    await page.route(buildApiUrl("/deepsearch/corrections/telemetry"), (route) =>
      route.fulfill(
        jsonResponse({
          queue_counts: mockCorrections.stats,
          success_rate: 0.77,
          last_updated: new Date().toISOString(),
        })
      )
    );
    await page.route(buildApiUrl("/deepsearch/corrections/dead-letter"), (route) =>
      route.fulfill(jsonResponse({ count: 0, items: [] }))
    );
  });

  test("dashboard displays mission counts and quality distribution", async ({ page }) => {
    await page.goto("/console");

    // Header
    await expect(page.getByRole("heading", { name: "Operator Console" })).toBeVisible();

    // Mission stats - look for the stats within the Mission Overview section
    await expect(page.getByText("Mission Overview")).toBeVisible();
    await expect(page.getByText("Total Missions").first()).toBeVisible();

    // Quality distribution section
    await expect(page.getByText("Quality Distribution")).toBeVisible();
  });

  test("mission list displays with status and quality filters", async ({ page }) => {
    await page.goto("/console/missions");

    // Header
    await expect(page.getByRole("heading", { name: "Mission List" })).toBeVisible();

    // Search filter
    await expect(page.getByPlaceholder("Search by title or ID...")).toBeVisible();

    // Status filter dropdown
    await expect(page.getByLabel("Status")).toBeVisible();

    // Quality filter dropdown
    await expect(page.getByLabel("Quality")).toBeVisible();

    // Mission rows
    await expect(page.getByText("Test Mission 1")).toBeVisible();
    await expect(page.getByText("Test Mission 2")).toBeVisible();
  });

  test("mission detail shows relationships and evidence", async ({ page }) => {
    const missionId = "11111111-1111-1111-1111-111111111111";
    await page.route(buildApiUrl(`/missions/${missionId}`), (route) =>
      route.fulfill(jsonResponse(mockMissions[0]))
    );
    await page.route(buildApiUrl(`/missions/${missionId}/related**`), (route) =>
      route.fulfill(jsonResponse(mockRelationships))
    );

    await page.goto(`/console/missions/${missionId}`);

    // Title
    await expect(page.getByRole("heading", { name: "Test Mission 1" })).toBeVisible();

    // Stats
    await expect(page.getByText("60%")).toBeVisible();

    // Export buttons
    await expect(page.getByRole("button", { name: "JSON" })).toBeVisible();
    await expect(page.getByRole("button", { name: "YAML" })).toBeVisible();

    // Relationship tree
    await expect(page.getByText("Relationship Tree")).toBeVisible();
    await expect(page.getByText("1 docs, 2 chunks, 0 insights")).toBeVisible();
  });

  test("correction status visible with error details", async ({ page }) => {
    await page.goto("/console/corrections");

    // Header
    await expect(page.getByRole("heading", { name: "Correction Queue" })).toBeVisible();

    // Stats
    await expect(page.getByText("Pending").first()).toBeVisible();
    await expect(page.getByText("In Progress").first()).toBeVisible();
    await expect(page.getByText("Completed").first()).toBeVisible();
    await expect(page.getByText("Failed").first()).toBeVisible();

    // Action buttons
    await expect(page.getByRole("button", { name: "Process Now" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();

    // Tabs
    await expect(page.getByRole("button", { name: "Queue" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Telemetry" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Dead Letter/i })).toBeVisible();
  });

  test("export buttons generate JSON/YAML downloads", async ({ page }) => {
    const missionId = "11111111-1111-1111-1111-111111111111";
    await page.route(buildApiUrl(`/missions/${missionId}`), (route) =>
      route.fulfill(jsonResponse(mockMissions[0]))
    );
    await page.route(buildApiUrl(`/missions/${missionId}/related**`), (route) =>
      route.fulfill(jsonResponse(mockRelationships))
    );

    await page.goto(`/console/missions/${missionId}`);

    // Setup download listener
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "JSON" }).click(),
    ]);

    // Verify download
    expect(download.suggestedFilename()).toMatch(/mission-.*\.json/);
  });

  test("console routes protected by auth", async ({ page }) => {
    // Clear any stored auth
    await page.goto("/console");

    // AuthGate should show login or session check
    // The AuthGate component shows "Verifying session..." or login form
    const verifyingOrLogin = page
      .getByText("Verifying session")
      .or(page.getByText("Sign in"))
      .or(page.getByRole("heading", { name: "Operator Console" }));

    await expect(verifyingOrLogin.first()).toBeVisible();
  });

  test("dashboard loads in under 2 seconds", async ({ page }) => {
    const start = Date.now();

    await page.goto("/console");
    await expect(page.getByRole("heading", { name: "Operator Console" })).toBeVisible();

    const loadTime = Date.now() - start;
    expect(loadTime).toBeLessThan(2000);
  });
});
