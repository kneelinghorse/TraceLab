# TraceLab Design Fingerprint Scan — Sprint 40 (T40.7)

**Scanned:** 2026-04-23
**Target:** https://tracelab.aquex.ai/ (TraceLab production)
**Scope:** Research artifact only — no UI implementation in S40. Captured for input to future OODS Foundry brand-token alignment, likely post-domain-migration.

## TL;DR

TraceLab production is a **Next.js + Tailwind + Inter** SPA with a clean Tailwind-aligned design vocabulary (4px spacing grid, 12/14/16/18/20/24/30 type ramp, 0/4/6/8/12/20/full radius scale). It uses **no CSS custom properties or design-token layer** — Tailwind utility classes are baked into JSX with hardcoded gray/blue/status palette values from Tailwind's defaults. The structural drift vs. OODS Foundry Brand A is therefore not chromatic but architectural: TraceLab has no token indirection, so any future brand alignment is a refactor of class strings, not a token override.

## Scan methodology

Two passes, both via Stage1 MCP:

| Pass | Tool | Coverage | Use |
|------|------|----------|-----|
| Unauthenticated | `stage1_inspect_app` + `stage1_inspect_surface` | 8 routes (login wall + nav shell) | IA outline only — computed styles came back as browser defaults (Times font, #0000ee link blue, 21.44px h1 margin) confirming the public surface is thin |
| Authenticated guided | `stage1_guided_start` → `stage1_guided_end` → `stage1_inspect_guided` | 17 routes, 91% coverage score, 1052 elements sampled | Real fingerprint — palette, typography, spacing, components |

Authenticated routes captured: `/missions`, `/missions/{uuid}` ×2, `/projects`, `/projects/{uuid}` ×2, `/documents`, `/documents/{uuid}` ×3, `/collections`, `/collections/{uuid}`, `/reports`, `/reports/{uuid}`, `/search`, `/console`, `/settings`. Only `/` (post-login dashboard) was missed; coverage tool noted +0.03 expected gain — not load-bearing for this pass.

## Information architecture

8 top-level routes, all under flat root namespace. Global nav surfaces all 7 content sections + brand mark (`TraceLab` → `/`):

```
/                  (home / post-login)
/missions          (list)   →  /missions/{uuid}    (detail)
/projects          (list)   →  /projects/{uuid}    (detail)
/reports           (list)   →  /reports/{uuid}     (detail)
/documents         (list)   →  /documents/{uuid}   (detail)
/collections       (list)   →  /collections/{uuid} (detail)
/search            (search interface)
/console           (debugging / system surface)
/settings          (user/system settings)
```

Page-type classifier sees all 7 content sections as `type=content` (confidence 0.95) and `/` as `type=home` (confidence 0.65). Pure list+detail pattern repeated across all entity types — no hub/dashboard, no kanban, no editor mode.

## Tech stack (inferred)

| Signal | Detected | Evidence |
|--------|----------|----------|
| Framework | **Next.js** | `#__next` root container present (cluster-1, 128 instances) |
| CSS framework | **Tailwind CSS** | Utility-class patterns dominate (`text-xl`, `max-w-7xl`, `rounded-xl`, `bg-gray-100`, `text-blue-600`, `dark:bg-gray-700`, `hover:bg-gray-50`) |
| Type | **Inter** + ui-monospace fallback | 1050/1052 sampled elements use Inter |
| Token layer | **None** | `theming.json`: 0 CSS custom properties, 0 theme blocks, 0 prefers-color-scheme handlers |
| Dark mode | **Class-defined but ungated** | `dark:` Tailwind variants present in CSS (e.g., `dark:bg-gray-700`, `dark:text-blue-400`) but no toggle mechanism, no `prefers-color-scheme` listener — appears unwired in production |
| Responsive | **Not detected** | `breakpoints.json` reports 0 breakpoints, 0 media rules — Tailwind's `md:`/`lg:` class variants were not picked up by Stage1's @media-rule scan; treat as inconclusive rather than confirmed-non-responsive |

## Typography fingerprint

**Family:** Inter (sans, 1050×) + ui-monospace (2×, code blocks only)

**Type scale** (px, by usage):

| Size | Tailwind | Count | Likely role |
|------|----------|-------|-------------|
| 12px | `text-xs` | 184 | Eyebrow / metadata / badges |
| 14px | `text-sm` | 460 | Body / table cells / form labels (dominant) |
| 16px | `text-base` | 292 | Reading body / inputs |
| 18px | `text-lg` | 56 | Section headers (h2/h3) |
| 20px | `text-xl` | 35 | Brand link / card titles |
| 24px | `text-2xl` | 16 | Page sub-titles |
| 30px | `text-3xl` | 9 | Page H1 |

**Line heights:** 16/20/24/26/28/32/36 — paired with the 7-step type scale, all token-aligned.

**Style observation:** No display/serif font in the stack. No fluid-type clamp() values detected. Bold weight (`font-bold`) and semibold (`font-semibold`) both used — semibold dominant on headings.

## Color palette

### Text (top values, all hex)

| Hex | Count | Role hypothesis |
|------|-------|-----------------|
| `#4b5563` | 234 | Primary body text — Tailwind `gray-600` |
| `#111827` | 200 | Heading / strong text — Tailwind `gray-900` |
| `#f1f2f4` | 106 | Light text on dark surfaces — near `slate-100` |
| `#2563eb` | 74 | **Primary accent** — Tailwind `blue-600` (links, buttons, active states) |
| `#6b7280` | 71 | Secondary / muted body — Tailwind `gray-500` |
| `#ffffff` | 67 | White text on filled surfaces |
| `#374151` | 56 | Heavier body text — Tailwind `gray-700` |
| `#94a3b8` | 48 | Muted on dark — Tailwind `slate-400` |
| `#e2e8f0` | 37 | Subtle text on dark — Tailwind `slate-200` |
| `#166534` | 35 | Status: success text — Tailwind `green-800` |
| `#dc2626` | 28 | Status: critical text — Tailwind `red-600` |
| `#a16207` | 21 | Status: warning text — Tailwind `yellow-700` |
| `#15803d`, `#16a34a`, `#047857` | 22 | Success variants — Tailwind `green-700/600/700` |
| `#ca8a04` | 7 | Warning variant — Tailwind `yellow-600` |
| `#4f46e5` | 3 | Info / indigo accent — Tailwind `indigo-600` |

### Background (top values)

| Hex | Count | Role hypothesis |
|------|-------|-----------------|
| `#00000000` | 824 | Transparent (default for most elements) |
| `#dcfce7` | 45 | Status: success surface — Tailwind `green-100` |
| `#f3f4f6` | 39 | Neutral surface — Tailwind `gray-100` (code blocks, table headers) |
| `#ffffff` | 36 | Card / panel surface |
| `#fef9c3` | 21 | Status: warning surface — Tailwind `yellow-100` |
| `#0d101c` | 18 | **Dark navy surface** — likely modal/console section |
| `#020617b3` | 16 | Modal scrim — Tailwind `slate-950` @ 70% alpha |
| `#2563eb` | 10 | Primary button fill — Tailwind `blue-600` |
| `#60a5fa` | 4 | Secondary action — Tailwind `blue-400` |
| `#d1fae5` | 3 | Success variant surface — Tailwind `green-100` |

**Palette observations:**
- **Brand identity is thin** — there's no proprietary accent color. The "TraceLab blue" is Tailwind's stock `blue-600` (#2563eb), which is the single most common pick across the entire React/Tailwind ecosystem. This matters when sub-brand work activates: there's no existing brand equity in the palette to preserve.
- **Status palette is well-formed** — green/yellow/red surfaces + matching darker text variants, all from Tailwind's status family. These are the cleanest tokens to alias when introducing OODS status mappings.
- **Dark surface (`#0d101c`) appears in only one cluster** — likely the console or a code-rendering panel. Suggests the app has at least one dark-themed region, but it's local, not theme-wide.

## Spacing + radii

**Padding scale (px):** 0, 2, 4, 6, 8, 12, 16, 24, 32 — clean Tailwind 4px grid; outliers `10` (×2) and `40` (×2) flagged as off-scale.

**Margin scale (px):** 0, 4, 6, 8, 12, 16, 20, 24, 32 + outlier `95` (×2, likely centering/hero margin on one route).

**Border radius (px):**

| Radius | Count | Tailwind equivalent | Role |
|--------|-------|---------------------|------|
| 0 | 2712 | `rounded-none` | Tables, inputs, plain elements |
| 4 | 400 | `rounded` | Default inputs, small buttons |
| 6 | 552 | `rounded-md` | Standard buttons / cards (most common rounded value) |
| 8 | 268 | `rounded-lg` | Larger cards / panels |
| 12 | 44 | `rounded-xl` | Featured surfaces |
| 20 | 4 | `rounded-2xl` | Rare — special cards |
| 9999 | 228 | `rounded-full` | Pills, badges, status dots, avatars |

**Spacing observation:** Default value is 0 (most elements have no padding/margin set explicitly — Tailwind utility classes layered on a stripped base). 8px is the dominant explicit padding (668×). 16px is the dominant explicit gap. This is textbook Tailwind tight-spacing UI.

## Component inventory

55 distinct cluster patterns detected, 3337 total instances, 41 patterns recurring across multiple pages. Top 15 by instance count:

| Cluster | Pattern | Selector | Tag | Instances | Inferred role |
|--------|---------|----------|-----|-----------|---------------|
| 14 | Border B | `td.px-4` | td | 1081 | **Table cells** — heaviest single pattern; tabular UI dominates list views |
| 4 | Container | `div.max-w-7xl` | div | 310 | **Page container** — 1280px max width, centered |
| 15 | Hover:Bg Gray 50 | `tr` | tr | 193 | **Table rows** with hover state |
| 20 | Rounded Full | `span.w-2` | span | 185 | **Status dots** / pill-shaped indicators |
| 0 | Font Bold | `a.text-xl` | a | 178 | **Brand-link / nav titles** |
| 3 | List Container | `div.flex` | div | 172 | **Flex layout containers** |
| 2 | Uppercase | `p.text-xs` | p | 148 | **Eyebrow labels** (uppercase metadata) |
| 7 | Font Semibold | `span` | span | 131 | **Strong inline text** |
| 9 | Rounded Xl | `button.w-full` | button | 109 | **Full-width primary buttons** (rounded-xl, distinct from inline buttons) |
| 17 | Dark:Text Blue 400 | `a.text-blue-600` | a | 103 | **Inline links** with dark-mode variant |
| 16 | Dark:Bg Gray 700 | `th.px-4` | th | 66 | **Table headers** |
| 38/49 | Option | `option` | option | 102 | **Select dropdown options** |
| 25 | Font Medium | `p.text-white/90` | p | 50 | **White-on-dark body text** |
| 19 | Font Semibold | `h2.text-lg` | h2 | 46 | **Section headings** |
| 13 | Border B | `nav.bg-white` | nav | 18 | **Global top nav** (white surface, bottom border) |

**By role tally:** unknown 30 / list 9 / input 4 / button 2 / form 2 / header 2 / section 2 / navigation 1 / card 1 / main 1 / aside 1.

**Component observations:**
- **Table-heavy UI.** ~1080 td cells across 17 pages = lists are the dominant interaction surface. Card or grid layouts are absent or rare.
- **Two button styles emerge:** `button.w-full` rounded-xl (large, prominent) vs. inline `button` elements with no class pattern. No button-component primitive — visual styling is per-instance.
- **Status dots (`span.w-2 rounded-full`) are reused 185×.** Strong candidate for the first OODS-aliased atom — single component, high reuse, semantic meaning (status).
- **No card primitive detected.** Detail views are likely flat columns of headings + paragraphs rather than card/panel composition.
- **No modal/dialog cluster surfaced explicitly** — modal scrim color (#020617b3) is in the palette but no clustered structure means modals are either rare or their structure is too heterogeneous to cluster.

## Drift report — TraceLab vs OODS Foundry Brand A

OODS Foundry Brand A token bundle (build 2026-04-23, dark theme, Tailwind platform) defines a token layer along these axes: brand-a/brand-b namespaces, status (critical/info/neutral/success/warning) × (surface/text), surface (canvas/raised/subtle/interactive-primary), text (primary/secondary/muted/on-interactive), border (strong/subtle), component-specific tokens (cmp-text-placeholder-*).

Brand A's resolved values use **CSS system color keywords** (Canvas, CanvasText, Highlight, HighlightText, GrayText) — i.e. OS-driven theming as the brand default. Drift is therefore as much *architectural* as it is *chromatic*:

| Axis | TraceLab | OODS Brand A | Drift type |
|------|----------|--------------|------------|
| **Token layer** | None — Tailwind classes inline | CSS custom properties (`--oods-brand-a-*`) | **Structural** — TraceLab has no indirection to override |
| **Color source** | Hardcoded Tailwind palette hex | System-color keywords (Canvas/CanvasText/Highlight) | **Chromatic + philosophical** — TraceLab opts for explicit hex; OODS opts for OS theme |
| **Status surfaces** | Tailwind green-100/yellow-100/red-100 + matching text-700 | `--oods-brand-a-status-{critical,info,neutral,success,warning}-{surface,text}` aliases | **Aliasing gap** — semantics line up but no name binding exists |
| **Surface hierarchy** | Implicit (white card on white page) | Explicit canvas/raised/subtle/interactive-primary | **Vocabulary gap** — TraceLab doesn't distinguish raised vs. canvas |
| **Text hierarchy** | gray-900 / gray-700 / gray-600 / gray-500 / slate-400 (5 levels) | primary / secondary / muted / on-interactive (4 named) | **Naming gap** — TraceLab has finer granularity but no semantic names |
| **Brand accent** | Tailwind `blue-600` (#2563eb) | Highlight (system) | **Identity gap** — TraceLab has no proprietary accent |
| **Dark mode** | `dark:` classes present, no toggle wired | OS-driven via system colors | **Wiring gap** — TraceLab has half the implementation |
| **Border tokens** | Hardcoded gray borders | `--oods-brand-a-border-{strong,subtle}` | **Aliasing gap** |
| **Component primitives** | No component library detected; per-instance styling | 109 catalog components across categories (lifecycle 16, core 15, primitive 14, viz.mark 13, viz.encoding 11, financial 10, behavioral 8, visual 7, content 6, communication 4, structural 3, viz.spatial 3) | **Coverage gap** — OODS has a much larger component vocabulary; alignment scope is large |

**No semantic drift detected by Stage1's drift_report.json** (semantic_drift: [], projection_inconsistency: [], capability_contradiction: [], token_intent_mismatch: [], object_coverage_gap: []) — but that's because the comparison runs against a *prior Stage1 run* of the same target, not against OODS. There is no prior run, so drift between scans is empty by definition. The OODS-vs-TraceLab drift above is hand-built from the artifacts.

## Palette recommendations (for future sub-brand work)

Three observations that should inform whatever palette comes next:

1. **There's no brand-equity loss to worry about.** Today's accent is Tailwind `blue-600`. If a TraceLab sub-brand wants to stake a different accent, no users will mourn the loss of #2563eb — it has zero proprietary identity. A legitimate brand color (something distinguishable from Atlassian, Linear, Notion, GitHub, every fintech, etc.) is wide open.

2. **Status palette is the cleanest first alias target.** Green-100/700, Yellow-100/700, Red-100/600 + dark text variants are all in Tailwind defaults and map 1:1 to OODS's status-{critical,success,warning,info,neutral}-{surface,text} 10-token group. First migration step that delivers visible, low-risk value.

3. **The dark-surface region (`#0d101c`) is an unexplored design vector.** It appears in one cluster (likely console or modal). If the future TraceLab brand wants to claim a dark-mode identity (matching DeepSearch's research-tool aesthetic, or differentiating from the white-page tool category), there's already a dark color in production to build on rather than introduce.

**Suggested palette starter (when sub-brand work activates):**

| Token | Suggestion | Rationale |
|-------|------------|-----------|
| `--brand-tracelab-accent` | TBD — needs design pick, but **not** Tailwind blue-600 | Today's accent is generic; sub-brand needs a proprietary one |
| `--brand-tracelab-canvas` | `#ffffff` (light) / `#0d101c` (dark) | Light keeps the current white surface; dark reuses the existing console color |
| `--brand-tracelab-status-{success,warning,critical,info,neutral}-{surface,text}` | Keep current Tailwind values, just alias them | Zero visual change, full token-layer benefit |

## Open questions / next steps

- **Is `dark:` variant adoption intentional but unwired, or vestigial?** Worth asking before brand work commits to a dark-mode strategy. (Tailwind classes exist; toggle does not.)
- **Is the table-dominant UI going to stay?** Current design is functional but visually uniform across entity types. Sub-brand work could differentiate detail views (cards, hero banners, viz primitives) without breaking the list views.
- **OODS Foundry component coverage gap is large** — 109 OODS components vs. ~10 distinct TraceLab visual primitives. Any "align to OODS" mission needs scoping; full alignment is months of work, partial alignment (status atoms + button + nav) is a sprint.
- **No prior Stage1 run exists** — future scans (post sub-brand work) will be able to use Stage1's `compareRunDir` parameter to produce a real semantic-drift report against today's baseline. Today's run dirs: `5200dec3-00d2-4c9f-b5eb-abd4e0777715` (unauth) and `guided-1776917221458` (authed).

## Raw artifact references

All scan output is on local disk under `out/stage1/tracelab-prod*/` (gitignored — research evidence, not code).

**Unauthenticated app-profile run:**
- `out/stage1/tracelab-prod/5200dec3-00d2-4c9f-b5eb-abd4e0777715/artifacts/`
  - `app_profile.json`, `ia_outline.json`, `style_fingerprint.json`, `token-guess.json`, `component_clusters.json`, `orca_candidates.json`, `capability_rollup.json`, `drift_report.json`, `a11y_report.json`, `perf_report.json`, `reconciliation_report.json`, `review_queue.json`, `identity_graph.json`, `object_rollup.json`, `identity_candidates.json`

**Unauthenticated surface run:**
- `out/stage1/tracelab-prod/2ca078c5-b905-425d-92a0-5d3d1805fda2/artifacts/`
  - `style_fingerprint.json`, `token-guess.json`, `surface_snapshot.json`, `baseline_metrics.json`

**Authenticated guided run:**
- `out/stage1/tracelab-prod-guided/guided-1776917221458/artifacts/`
  - 18 artifacts including `style_fingerprint.json` (9.8KB — the canonical fingerprint for this report), `token-guess.json`, `theming.json`, `breakpoints.json`, `component_clusters.json` (157KB — full component inventory), `orca_candidates.json` (1MB — full ORCA model), `coverage_status.json`, `entity_catalog.json`, `composition_patterns.json`

**OODS Foundry Brand A token bundle (build 2026-04-23):**
- `/Users/systemsystems/portfolio/Design-Tools/OODS-Foundry-mcp/artifacts/current-state/2026-04-23/tokens.build/`
  - `tokens.dark.json` (1MB), `tokens.css` (80KB), `tokens.ts` (908KB), `tokens.tailwind.json` (1MB), `transcript.json`, `bundle_index.json`
