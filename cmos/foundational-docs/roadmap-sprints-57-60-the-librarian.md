# TraceLab — Vision and Roadmap: The Librarian (Sprints 57–60)

**Status:** Living document. Authoritative for INTENT; CMOS is authoritative for STATUS.
**Opened:** 2026-09-17, at Sprint 57 planning.
**Predecessor:** `roadmap-sprints-50-53-ux-overhaul.md`, which carried Sprints 50–56 and is now closed to new sprint sections.
**Guiding template:** [roadmap_template.md](roadmap_template.md). Follow-on product work is recorded below the Librarian sprint plan; CMOS holds its acceptance criteria and status.

Revisit this document at **every sprint open and every sprint close**, the same way its predecessor was maintained: at close, rewrite the closing sprint's section as outcome; at open, re-plan the opening sprint's section from the CMOS missions; append a dated line to the Change Log either way. A sprint is not closed while its section here still reads as a plan.

---

## Vision Statement

TraceLab already does the hard part: it runs real research, keeps the evidence, and lets you audit any claim back to its source. What it does not do is help you *ask*. Every mission today is hand-authored by someone who already knows how to author missions, and the only person who has ever run one is Derek.

The Librarian closes that gap. It is an agent that **operates TraceLab's existing machinery on a user's behalf** — authoring missions, synthesising research, assembling reports from chunks the system already holds. It converses like any other chat agent too (Rule 1, amended 2026-09-18), but that is not what makes it worth building: the corpus, the tools and cited provenance are. The evidence ledger stays the point of the system rather than decoration because every claim about the corpus carries its source.

> "using the exising tools to do work" — Derek, 2026-09-17

---

## The two rules this arc is built on

Everything below follows from two constraints. Both came out of the Sprint 56 review conversation, and both are cheap now and expensive to retrofit.

### Rule 1 — Artifacts are the point, not the gate

**AMENDED 2026-09-18 by Derek (decision #513, superseding #511).** The original rule said every turn must end in a TraceLab artifact or end in nothing, derived from his anti-goal *"i'm not trying to make it a backdoor way for someone to have a chat account."* He struck that constraint himself:

> "i amend or strike my previous want to avoid a backdoor chat subscription, lets give it the broader ability to do q&a or just chat just like any other chat agent, but this one also has acess to our corpus and tools?"

So **the Librarian converses freely.** General questions get real answers. Open Q&A is in scope. It behaves like any other chat agent, with the corpus and the tools additionally available.

What remains is an emphasis rather than a gate: **turning a conversation into an artifact should always be one action away** — a mission, a report, a collection — without the Librarian ever refusing to just talk. The risk the original rule was defending against was never really a chat subscription; it was the Librarian becoming a worse general chat agent that happens to have your documents attached. Making artifacts the obvious next move defends against that without crippling the conversation.

### Rule 2 — The boundary is on claim type, not capability

The first version of this plan bounded the Librarian to corpus-only knowledge. Derek rejected it, correctly:

> "How do you bound it? doesn't that make creating new missions harder? The agent can help make good prompts using that knowledge of the world and connecting some dots for users on what and how to look for the right info."

> "i think this makes it a harder start for new people with a bounded librarian, no? there's no corpus for them, so the agent has nothing to pull from?"

So the boundary moved off capability and onto **what kind of statement carries provenance**:

| Statement type | World knowledge | Citations |
| --- | --- | --- |
| Claims **about the corpus** — "we found X", "three documents cover Y", "this contradicts the March report" | allowed as context | **required, always** |
| Planning, prompt authoring, connecting dots, "that question is too broad" | **free rein** | not applicable — asserts nothing about the corpus |

The UI renders the two differently, so a user always knows which they are reading. If the Librarian cannot cite, it does not assert.

**This dissolves the cold start.** An empty Space has nothing to cite, so a new user's Librarian is entirely in planning mode by default. The mode falls out of what is asked; there is nothing to configure. The empty state becomes the funnel rather than a dead end.

**Rule 2 is now load-bearing in a way it was not when written.** Under the old Rule 1, a user could infer provenance from the shape of the interaction — a turn produced an artifact, so it was grounded work. With free conversation allowed, world knowledge and corpus claims appear in the *same reply*, and the citation display becomes the only thing distinguishing them. It has gone from a supporting nicety to the product's integrity guarantee, and it is mutation-tested in both directions: a fabricated citation must fail, and an uncited corpus claim must fail.

---

## Where We Are (2026-09-17 baseline, verified against production)

| Fact | Value | Why it matters |
| --- | --- | --- |
| Documents | 1,616 | A real corpus exists to be librarian *of* |
| Chunks | 16,719 | Retrieval has something to retrieve |
| Reports | 487 | |
| Missions | 437 | **All 437 owned by `derek@deniedart.com`** |
| Ledger entries | 6,118 | The system already accumulates knowledge about itself |
| Collections | 53 | |
| Projects | 54, zero soft-deleted | Cleaned at Sprint 56 close |
| Users | 8 | |
| Spaces | Default (35 projects), Derek-Private (17), Parts Town (2), Personal Archive (0) | |

**Nobody but Derek has ever run a mission.** Syndy has had a Space and access since before this arc opened and has run zero. So the multi-user path is not being scaled — it is being used for the first time.

**A project lives in exactly one Space.** `projects.workspace_id` is a single FK and zero projects are unassigned. Two guests cannot share a seeded reference corpus without duplicating the project or placing them in the same Space — and only an admin can do either. **Resolved into Sprint 58** (decisions #514, #516); guest invitations are gated on it.

**Missions record no cost.** `reports.tokens_used` and `synthesis_cache.tokens_used` exist; the expensive operation — a DeepSearch run — has no usage column at all.

**The cited-answer test is skipped.** `test_rag_pipeline_generates_cited_answer` fails when un-skipped: the pipeline never reaches the retrieval stub. The product's central promise has no live test.

---

## Why this arc, and why now

RBAC ran from Sprint 43 to Sprint 49 and shipped. Sprints 54, 55 and 56 returned to it and produced diminishing real work: RBAC-2 and RBAC-4 were created and dropped the same day in S55; a production cron was built and deleted within the hour in S56. Derek named it — *"we're kind of spinning right now on rbac stuff, this is several in a row now."*

The diagnosis in the Sprint 56 review was that the real RBAC backlog ran out around S49 and scope was being invented to fill sprints. **This arc contains no RBAC missions.** Access control gets exercised here the way it should be — by real users doing real work, in WALK-1.

---

## Implementation Plan

### Sprint 57 — The Librarian, Part 1: Authoring (opened 2026-09-17, closed 2026-09-22, five of five)

**Goal:** Ship the surface that works on day one for a user with no corpus, and find out what breaks when someone other than Derek uses the system.

Missions (CMOS is authoritative for status):

- **LIB-0 — Research the build, using TraceLab to decide how to build TraceLab.** A real DeepSearch mission on grounded tool-operating agents as of late 2026; its report becomes LIB-1's design reference. Deliberately dogfooded. Findings that change LIB-1's design are recorded as decisions *before* LIB-1 is built. **Completed 2026-09-18, closed 2026-09-22** (report document `LIB-0_report.md`, 301 ledger entries, decision #517).
- **LIB-1 — The mission-authoring assistant.** Conversation in, a real DeepSearch mission out. World knowledge free for shaping the question, free conversation allowed, and the claim-type boundary enforced by test in both directions. Criteria rewritten 2026-09-18 under decision #513. *Requires LIB-0.* **Shipped 2026-09-22** (PRs #349, #350; decisions #519, #520; learning #236): `/librarian`, two stages behind one provider seam, server-side provenance validator, explicit idempotent creation. Proven by mission `TRACE-SHARE-58`, authored by the deployed Librarian and run unmodified: 226 sources, 41 verified references, 360 ledger entries, 4 m 20 s. Receipt: `cmos/reports/sprint-57/LIB-1-production-run/`.
- **WALK-1 — The guest path, walked.** Derek and the agent watch a mission run end to end from a fresh Space, as a new design pro would, ideally as a non-privileged principal. Supersedes next-steps #330 and #355, deferred across four sprints. **Walked 2026-09-22** (session PS-2026-09-22-005; decisions #524, #525; learning #238): Derek, as a fresh `member` account in its own Space, went from an empty project through four Librarian turns to a draft, a created mission and a submitted run that completed in five minutes on DeepSeek Flash, the first production mission not run by Derek. Eight findings, each with request-log or database evidence: the transcript is lost on navigation, a successful draft renders offscreen in silence, the two-step flow is unexplained, the draft CTA is faint, the transcript box is tight, a guest's new project lands in Default Workspace rather than the guest's Space (the criterion-5 answer), the Evidence badge needs every entry viewed to clear, and "DeepSeek translates evidence" turned out to be foreign-language sources (1.2% of entries). The five Librarian findings are LIB-2 in Sprint 58 with Derek's decisions attached; the two-step create-then-submit stays by his choice. Also confirmed live: DeepSearch posts mission logs as one batch after completion, which is the real reason there is no in-progress feed; asked of DeepSearch in message `1621f451`. Receipt: `cmos/reports/sprint-57/WALK-1-guest-walk/`.
- **METER-0 — Record what a mission costs.** Data only. No quotas, no limits, no billing, no user-visible surface. **Shipped 2026-09-22** (PRs #353, #354; decision #522; learning #237): `usage_records`, one row per DeepSearch run and per Librarian call, attributed to the submitter; the reconciler's first tick recorded all 440 historical runs; `GET /admin/usage` answers last month per user. Receipt: `cmos/reports/sprint-57/METER-0-production-check/`.
- **RAG-1 — Diagnose the skipped cited-answer test.** Root cause named, not worked around; explicitly not an SDK upgrade. **Done 2026-09-22** (PR #355; decision #523): the test was wired to a retrieval seam B21.8 replaced with the PEDR orchestrator in December 2025; now un-skipped, green, and mutation-proven three ways. Escalated separately: the synthesis path mints citations from unmatched model output and invents a top-chunk fallback, confirmed live; to be fixed before Sprint 59's Q&A surface. Receipt: `cmos/reports/sprint-57/RAG-1-diagnosis/`.

**Out of scope, deliberately:** any corpus Q&A surface, any automatic write to existing records, any RBAC mission, any metering policy.

### Sprint 58 — Good working order: the WALK-1 adjustments, the rewalk, and personal Spaces (opened 2026-09-22, closed 2026-09-23, six of six)

**Re-scoped at Sprint 57 close (decision #526).** The slot held sharing; Derek moved it: *"i'm not sure what sharing firts means, i want it to be in good working order before i bring people in, so lets proceed with the adjustments we just discussed and i'll rewalk it and go from there."*

**Goal:** Fix what the live guest walk found, then walk it again. Nothing new is designed; every mission traces to a WALK-1 finding and to Derek's decision on it.

Missions (CMOS is authoritative for status):

- **LIB-2 — Librarian orientation and persistence.** Findings 1, 3, 4, 5, 6 under decision #525: the transcript survives navigation, a successful draft is scrolled into view and announced, the mission page orients a user arriving from the Librarian (dismissable, remembered), the Draft button becomes the call to action when the model says there is enough, and the transcript gets room. The two-step create-then-submit stays exactly as it is; the colour meter is not built. **Shipped 2026-09-22** (PR #358, `ff0dc98`; decision #527): persistence in per-user localStorage with the server still stateless, focus and a toast after Draft, a three-step strip plus a `?from=librarian` notice behind one remembered dismissal, Draft as the primary button on the model's signal, a wider column and taller transcript with an Expand toggle. Verified on production by a read-only live check and a four-shot baseline with zero failures. Accepted when WALK-2 passes. Receipt: `cmos/reports/sprint-58/LIB-2-librarian-baseline/`.
- **GUEST-1 — A guest's new project lands in the guest's Space.** Finding 2: `default_workspace_id()` sends every new project to Default Workspace regardless of caller. The rule for members with one Space is decided with Derek's words and Derek's own creation path is unchanged unless he says otherwise. **Shipped 2026-09-22** (PR #360, `34b6c30`; decision #528 "ok for now"): a non-privileged member of exactly one Space creates there; everyone else, and every other create path, keeps Default. Verified in production as the guest. Receipt: `cmos/reports/sprint-58/GUEST-1-BADGE-1/`.
- **BADGE-1 — The Evidence badge clears without paging through a run.** Finding 7: the badge is the activity new-count per entry and one run adds hundreds. **Shipped 2026-09-22** (same PR; decision #528 "marked on open of the entire group of evidence"): the badge was already one item per run-group, but nothing ever marked a group viewed; `PUT /activity/viewed/evidence` now does, from the Evidence page and the mission's Evidence tab. Verified in production on the WALK-1 run: one call, badge 1 to 0.
- **WALK-2 — The rewalk.** Derek walks the guest path again on the fixed build, ideally with the DeepSearch log flush landed so the Runner logs panel fills during the run (next-step #412). **Walked 2026-09-22**, unwatched, as the guest on `3f2dd9c`: mission `2dedcb41` ran to completion (243 ledger entries); his one observation was that the draft reframed a research outcome into a deliverable and the pre-submit feedback said so, "very nice touch". His sentence on the gate: *"walk is done, close it out. its fine for now."* (decision #531). Logs still arrived as one batch after completion, so #412 stays open. Receipt: `cmos/reports/sprint-58/WALK-2-rewalk/`.

**Added 2026-09-22 after the rewalk (decision #530, scoped in decision #531): the Space model takes the Google Drive shape.** Derek's concern, on seeing that a spaceless member's project lands in Default Workspace: every user should have a personal Space created with the account, new projects should default there, shared Spaces stay all-or-nothing, and single-project sharing is a later layer. Built before people come in, because the first thing a new person does is create a project. His answers to the six scoping questions are decision #531 ("yes to both" on his own account and Derek-Private; "agree" on Default Workspace staying his legacy bucket; "fine, we're doing both either way"; "thats fine for now" on member-facing UI; "yes" on naming).

- **PERSONAL-1 — Personal Spaces: every user has one, and new projects land there.** Migration 052 adds one nullable, unique owning-user column on `workspaces`; the backfill creates one personal Space per human user, designates Derek-Private as Derek's, and moves projects owned by non-privileged members out of Default Workspace (today exactly one, the guest's). Both account-creation routes call one idempotent helper. `default_workspace_id()` returns the caller's personal Space for any human caller; the GUEST-1 sole-Space rule is removed. The admin page labels personal Spaces and refuses to add members to one. Verified in production as the guest and as Derek. **Shipped 2026-09-22** (PR #363, `fec1893`; the placement rule is decision #532, recorded before code). The backfill made eight personal Spaces. Derek-Private became Derek's, and the other seven are named for their users. The guest's `d2d6519c` left Default with its two documents, two missions and two reports; Derek's 36 live projects stayed in Default and child drift was untouched. In production the guest's new project landed in their personal Space and Derek's (through his MCP credential) in Derek-Private, and adding a member to a personal Space answered 409. The guest was disabled again. The first `/admin/spaces` baseline at 390px squeezed project names beside the longer Space labels; PR #364 (`fe4c112`) fixed it, and the re-run baseline is in the receipt. Receipt: `cmos/reports/sprint-58/PERSONAL-1/`.
- **PERSONAL-2 — Creating inside a shared Space** (*Requires PERSONAL-1*). A non-admin route lists the caller's Spaces; `POST /projects` accepts an optional Space validated against membership; the create form and the Librarian's inline create show a picker only when the caller belongs to more than one Space, defaulting to "My Space". Nothing else on the project hub changes. May slip to Sprint 59 without blocking the invite gate. **Shipped 2026-09-22** (PR #366, `2bcc766`; design decision #533, recorded before code): `GET /spaces` lists the caller's Spaces; `POST /projects` takes an optional `workspace_id` that members may use only for Spaces they belong to (403 otherwise, even for a Space that does not exist), and owners and admins may use for any existing Space; one picker serves the create form and the Librarian; the MCP create takes the same field. Verified in production through the real picker: the guest, in the shared Walkthrough Guest Space with the Test account added as a second member, created a project there, the second member's project list showed it, and the guest was refused for a Space they are not in. The temporary membership was removed and the guest disabled again. Receipt: `cmos/reports/sprint-58/PERSONAL-2/`.

**Outcome, at the close on 2026-09-23.** All six missions shipped inside two days. Every WALK-1 finding Derek ruled on was fixed: LIB-2, GUEST-1 and BADGE-1. The rewalk passed (WALK-2). Personal Spaces then landed in two build sessions, as Derek sized them. PERSONAL-1 gives every user a Space of their own, created with the account, where their new projects land. PERSONAL-2 lets a member of a shared Space choose to create in it, with the same membership check for the UI, the Librarian and the MCP. GUEST-1's sole-Space placement lasted about six hours before PERSONAL-1 replaced it. At the close, decisions #528 and #529 were superseded by #534, which keeps their BADGE-1 halves, and the GUEST-1 receipt carries a correction note. The close also recorded two process lessons. A clean smoke summary can hide a squeezed 390px layout (learning #242). Two pytest processes must never share the SQLite test file (learning #243). The 200 ms graph gate now times the graph layer with garbage collection off (PR #367). Every open next-step was carried to Sprint 59, including the invite-gate reading only Derek can confirm (#432), child-row Space drift (#431), and the RAG citation fix (#417) and answer length (#401) that gate Q&A.

**Invite gate, read together:** decision #526 gated invites on the rewalk, which passed; decision #530 puts personal Spaces before bringing people in. Invites go out when PERSONAL-1 ships. It shipped on 2026-09-22. Derek then took invites off the gate list (decision #535): "i'm going to handle invites and its not on a timetable right now. I'll send them myself for now."

**Out of scope, deliberately:** project-level sharing (below, deferred; personal Spaces are placement, not sharing), corpus Q&A, autonomous writes, RBAC missions, metering policy, the search-page citation fix (next-step #417, before Sprint 59), any member-facing Space UI beyond PERSONAL-2's picker, and the pre-existing drift between child rows' Space column and their project's (harmless for access; a next-step).

### Sharing, as Derek means it (deferred past Sprint 58, decision #526; the analysis stands)

**Moved into the Sprint 58 slot 2026-09-18 (decision #514) because every guest invitation was thought to be blocked on it; moved out again 2026-09-22 because Derek wants the walked path in good working order first. Re-sequence after WALK-2.**

Derek described the model he believed existed:

> "the idea should be the person who creates the project is owner, can add others, they can then use/see that folder and use it. I suppose we could have grants like view/edit but otherwise, yes, meant to be shared between n number of people."

**It does not exist.** Verified against the tree: no `project_members` table, no `ProjectMember` model, and no "add people to this project" control anywhere in the frontend. The only membership table is `space_members`; the only sharing UI is `/admin/spaces`, behind `RequireAdmin`. What he did with Syndy was the admin Spaces flow — create a Space, assign two projects, add her as a member.

Three consequences, in order of severity:

1. **Only an admin can share anything.** A guest who creates a project cannot add anyone to it — they must ask Derek, from a page they cannot see. For "design pros try it out" that is a hard stop.
2. A project lives in exactly one Space, so sharing with two groups means merging those groups.
3. No view/edit grants exist. `space_members` carries a role, but access is all-or-nothing per Space via downward inheritance.

**This is the deferred phase of decision #196, not a reversal of it.** #196 locked Space-level grants with downward inheritance and explicitly deferred per-resource `resource_grants` to "Sprint D optional". This is that phase.

Requirements settled so far:

- Project-level membership with per-member grants (view/edit), administered by the **project's owner**, not an admin.
- **The blast radius is shown at the moment of sharing** (decision #516, Derek's own request): whoever shares must be told, in the flow, what the person they are adding will actually be able to see — specifically that a grant running through a Space is not confined to the project in front of them. This is the exact mismatch Derek nearly hit himself.
- Design recommendation, not yet ruled on: make project grants *genuinely* per-project rather than sugar over Space membership. If "add someone to this project" silently joins a Space, that warning becomes permanent scar tissue on the UI.

### Sprint 59 — Q&A, and the search question answered (opened 2026-09-23, closed 2026-09-24, seven of seven)

Corpus Q&A, now a headline capability rather than something to work up to, since Rule 1 was amended. Gated on RAG-1 from Sprint 57: a Q&A surface over a retrieval path whose cited-answer test does not run makes every wrong answer ambiguous — bad retrieval or bad generation, unknowable.

**Search is absorbed, not retired.** Derek asked whether the two coexist:

> "Right now, our search page is not unlike a chat bot in some ways already in that it returns chunks but we call an LLM to synthesize the chunks and provide a response. I've notiece those responses get truncated... Probably good to have search remain for the mcp surface. so the service wouldn't go away but not sure about the UI."

Settled: the Librarian becomes the primary surface, and a **chunk list stays one of the things it can render** — scanning twenty chunks for a half-remembered quote is a genuinely different job from asking a question, and it is exactly the job the org case describes. A saved chunk list is a collection, which is an artifact. The `/search` service and its MCP surface are untouched. The standalone page retires in this sprint, not before — and mind the ALIAS-1 trap, where a sibling dynamic route kept answering 200 after the page was deleted.

**The truncation is diagnosed, and the default is raised.** `app/core/config.py:50` set `rag_default_max_tokens = 350` — roughly 260 words — and the frontend never sends `max_tokens`, so every synthesis used that hard default. Not a rendering or streaming bug; a config default nobody revisited. PR #348 (`4feb3e3`, 2026-09-18) raised it to 1500; this section and next-step #401 kept saying 350 until the 2026-09-23 review checked the claim against the tree. **In production it is still 350** (found by RAG-3, 2026-09-23): Railway sets `RAG_DEFAULT_MAX_TOKENS=350` on the TraceLab service, as `.env.example` does, and that overrides the code default, so the raise never reached a production answer. **Settled per request** by the approved plan (decision #538) and built by QA-1 (decision #543). The Librarian sends a Short answer (600 tokens) or a Full synthesis (2000), and the model is told its length, because a citation label costs 33 tokens and a 350-token answer with four labels was cut off. The setting stays the default only for callers that send no budget.

**The plan (2026-09-23, decision #538).** Derek: "create the sprint and missions in cmos so that we can hand this off to a fresh agent session and get this set of work done." Four missions, filed in CMOS with Requires edges, in build order; each runs in its own fresh build session and is merged, deployed and verified in production before the next starts.

- **RAG-2 — Citations that resolve, or nothing.** The RAG pipeline stops inventing citations (labels that match no retrieved chunk are dropped, the top-chunk fallback goes) and short-circuits with an explicit nothing-found result when retrieval is empty; each fix carries a test proven by mutation. Replaces the RAG-1 escalation. First, because every answer below flows through this path. **Shipped 2026-09-23** (PR #374, `949c7a6`; receipt `cmos/reports/sprint-59/RAG-2/`): all three fixes, each mutation-proved, and `no_evidence` on the search response. Its production probes found that search hands the model chunks with no text, so RAG-3 was added ahead of QA-1.
- **RAG-3 — Retrieval keeps each chunk's text** (added 2026-09-23 from RAG-2's production finding). PEDR fusion keeps the whole record from whichever layer ranked a chunk best, and the graph layer's records carry no text, so every chunk the graph ranks above semantic reaches the model empty. On production a real question about TraceLab Research got five such chunks and the answer "no information". The fix repairs fusion, keeps chunks without text away from the model, applies an explicit project filter to graph results for every caller, and is accepted on production with a real question whose citations open. **Shipped 2026-09-23** (PR #376, `4d8257d`; receipt `cmos/reports/sprint-59/RAG-3/`): all three fixes, each mutation-proved. On production the model now reads real text (about 4,000 tokens where RAG-2 saw none), every citation opens at its chunk, and POST /pedr/search returns content on every result. The same probes found the model shown a neighbour of the chunk that answers, so RAG-4 was added ahead of QA-1.
- **RAG-4 — The model sees the chunks that answer the question** (added 2026-09-23 from RAG-3's production finding). Both of RAG-3's answers cited real text and still said the fact was not there. Graph expansion is seeded with the top ten matches and never ranks a seed itself, so the seeds' neighbours outrank them: the chunk that answers the PII question is first with the graph layer off and fifteenth with it on. And compression's 0.7 similarity cut sits above every similarity production produced (at most 0.66), so exactly one chunk reaches the model. The fix keeps the best matches in front and lets more than one relevant chunk through, accepted on production with a question whose answering chunk is known in advance and an answer that states the fact. QA-1 waits on it. **Shipped 2026-09-23** (PR #378, `65b11ef`; receipt `cmos/reports/sprint-59/RAG-4/`): the graph layer ranks its seeds first, so a best match can no longer fall below its own neighbours, and compression's cut is 0.4, set from similarities measured on production (answering chunks 0.425–0.664, unrelated 0.399 at most). Both fixes are mutation-proved. On production the PII chunk is first again with the graph on, and two questions got answers stating the fact from the chunk that holds it ("92% of 32-token inputs", "$48–$63" a month). QA-1 is next.
- **QA-1 — Ask the Librarian a question about the research.** One Q&A service function that is the only Q&A path; on the Librarian page an answer whose every citation opens a real chunk or evidence entry, corpus claims separated from world knowledge, refusal when the project cannot support the question, and an answer budget chosen per request (closing the single-default question above). Accepted on production against a real project. **Shipped 2026-09-23** (PR #380, `ccade35`, and follow-up #381, `b140085`; receipt `cmos/reports/sprint-59/QA-1/`). `answer_question` in `app/services/corpus_qa.py` is the one Q&A path, with the search route's scope, and MCP-6 will call it. The Librarian's "Ask the documents" mode renders cited passages that link to their chunks, and uncited text as plain prose. A question is refused before any model call when no chunk reaches the 0.4 floor, and refused when the answer cites nothing. The page sends a Short answer (600) or Full synthesis (2000), the model is told its length, and the semantic cache now matches on the budget. On production, three questions about TraceLab Research got answers citing the chunks that hold their facts, every link opened its chunk, and RAG-4's Kubernetes question (0.374) was refused with no model call. The first run found a range citation left as raw text and a long chunk's header scrolled off screen, both fixed in #381.
- **QA-2 — Search absorbed into the Librarian.** A plain chunk list the Librarian can render and save as a collection; the standalone Search page retires with a redirect, checked on production against the ALIAS-1 trap; the `/search` service and the MCP search tool untouched. **Shipped 2026-09-23** (PR #383, `814c166`, decision #545; receipt `cmos/reports/sprint-59/QA-2/`). The Librarian's "List the chunks" mode lists the 20 best chunks for a phrase from `POST /pedr/search`, not `POST /search`, because the list needs the full ranked list and the lexical layer without a model call. Each chunk opens at its place in its document. A list saves as one collection in rank order, and a phrase saves as a saved search. Saved searches run in the Librarian through their execute call, which counts the run. `/search` is a 308 to `/librarian` that keeps its query, and the palette's Recent searches went with the page, since nothing records the list's queries. On production every URL under `/search` either redirects or is a 404, the build has no `/search` page, `/search?q=Qdrant` in TraceLab Research lands on 20 named chunks whose first link opens its chunk, and the baseline of `/search`, `/librarian` and the list passed 12 of 12. MCP-6 is last.
- **MCP-6 — The same Q&A over the MCP.** `tracelab_search` gains an `ask` action over the shared service, same citation rule and access scope, with an MCP-client test proving cross-project denial; released as 2.1.0 by Derek's publish. **Shipped 2026-09-23** (PR #385, `0bff859`, decision #547; receipt `cmos/reports/sprint-59/MCP-6/`). `POST /api/v1/search/ask` loads the project (404), authorizes it for the caller (403) and calls `answer_question`, nothing else. Service principals are refused, and each paid call is metered as a `search_ask` usage row. `tracelab_search ask` returns the answer, its passages, the citations with a browser url that opens each chunk, and the nothing-found flag, making 9 tools and 50 actions. Derek published 2.1.0 at 23:58:41Z, byte-identical to the dry run. Installed fresh, the published package passed 19 of 19 on production: a cited answer whose link opens its chunk, the refusal for an unsupported question, and the API's 404 for an unknown project.

MCP-5 shipped @aquex/tracelab-mcp 2.0.0 on 2026-09-23 (decision #535; receipt `cmos/reports/sprint-59/MCP-5/`). **Out of the sprint:** sharing (Derek, 2026-09-23: "don't care, no"), invites (his, no timetable), everything else; the small leftovers stay on the ledger and are not raised with him unless he asks. Planned end date 2026-10-07; closed 2026-09-24.

**Outcome, at the close on 2026-09-24.** All seven missions shipped on 2026-09-23. Each was built in its own session, and merged, deployed and verified on production before the next began. The answer path came first, because every answer flows through it:

- **RAG-2** stopped the pipeline inventing citations and made empty retrieval an explicit nothing-found result.
- **RAG-3** and **RAG-4** were added mid-sprint from production probes. The model had been reading chunks with no text. Once it had text, the best matches ranked below their own neighbours, and only one chunk reached the model.
- **QA-1** then built the one Q&A service on that pipeline. The Librarian's "Ask the documents" answers with passages whose citations open their chunks. It refuses a question no chunk supports before any model call, and takes its budget per request, which settles the truncation Derek reported on 2026-09-18.
- **QA-2** retired the Search page into the Librarian's chunk list. `/search` redirects there, checked on production against the ALIAS-1 trap.
- **The MCP** shipped twice. 2.0.0 (MCP-5) carried ACT-1's removals and PERSONAL-2's Space choice. 2.1.0 (MCP-6) gives agents the same Q&A through the same service as `tracelab_search ask`. Derek published both, and each registry tarball matched the agent's dry run.

The close's receipt re-verification found stale citations in one receipt: RAG-2's cites code that later missions fixed or moved, and it now carries correction notes. The sprint's process lessons are learnings:

- the semantic cache serves a repeated question for 24 hours, so re-asking proves nothing new (#254, #257);
- local tests could reach production's Qdrant (#256);
- two receipt-tooling traps (#259, #260).

Every open next-step was carried to a Sprint 60 shell, 23 in all. They include Railway's 2026-12-01 deadline for `railway.json`, where the backend's start command runs the migrations.

### Sprint 60 — Finish the Librarian: suggestions, organisation and cited reports (opened 2026-09-29, closed 2026-09-30, six of six)

**Goal:** Finish the remaining Librarian capabilities and accept the complete journey on the deployed build. Derek asked to detail Sprint 60 for a fresh build session and "wrap up the librarian arc and make sure its all ready to go." He chose **one selected project** for organisation and duplicate suggestions. Decision **#551** records the plan; the [build handoff](../planning/sprint-60-HANDOFF.md) names the implementation seams, validation contract and carried-item dispositions. CMOS holds the full mission criteria.

**All six missions completed; the Librarian arc is accepted.** [REPORT-1](../reports/sprint-60/REPORT-1/README.md), [LIB-3](../reports/sprint-60/LIB-3/README.md), [DUP-1](../reports/sprint-60/DUP-1/README.md), [ORG-1](../reports/sprint-60/ORG-1/README.md) and [LIB-4](../reports/sprint-60/LIB-4/README.md) shipped in order. [WALK-3](../reports/sprint-60/WALK-3/README.md) then exercised the complete old/new journey as a dedicated temporary member in controlled empty/populated projects, including real generation, explicit acceptance, source navigation, exports, published MCP 2.1.0 and scoped negative probes. Thirty deployed page checks covered both themes at 390/820/1440; retries preserved exact artifacts and manual edits, with no model work on navigation or focus. The account is disabled and its key revoked. This is agent verification, not Derek's personal walkthrough, and no new DeepSearch research run was submitted. All five earlier production receipts and their current source/decision mechanisms were reverified.

**Simplified 2026-09-18 by decision #515.** Derek ruled out autonomous writes permanently, not as a staging decision:

> "no librarian is always asked and always has a given prompt or context. No ad hoc writes from an auto or chron. auto jobs should only ever be low risk, or suggested, like drafting a mission idea. i would still need to run it or if we did de-duping for instance, it would be presenting those as options as to how to remediate."

The suggestions are requested, reviewed and accepted in the Librarian; a persistent global queue or scheduler is not required. Sprints 57–59 already delivered mission authoring, guest/personal-Space readiness, corpus Q&A and chunk search. The accepted outcomes are:

| Order | Mission | Accepted outcome |
| --- | --- | --- |
| 1 | **REPORT-1 — Durable report citations** | The exact citation-to-chunk mapping survives saving, reopening and export; legacy gaps stay explicit |
| 2 | **LIB-3 — Project-description proposals** | Review/edit/accept a description, retain generated/accepted provenance, and safely restore the prior value |
| 3 | **DUP-1 — Duplicate review** | Compare exact/probable duplicate documents and remediation options without merging or deleting anything |
| 4 | **ORG-1 — Themed collections** | Review proposed document/chunk groups and explicitly save only the collections the user chooses |
| 5 | **LIB-4 — Report assembly** | Draft a report from reviewed project material, then save that exact cited draft with no second model call |
| 6 | **WALK-3 — Deployed arc acceptance** | Verify old and new journeys, source links, human-control boundaries, UI/accessibility and MCP reads; close the arc with receipts |

**Report choice, settled before build:** retain Report as the saved synthesis artifact and keep DeepSearch result Documents and links. Next-step #405 exposed a real prerequisite: report detail discarded the transient citation list, and the synthesis list lost the original numeric markers. REPORT-1 now makes those mappings durable; it does not fabricate support from input-source order or mass-regenerate historical reports. Learning #261 distinguishes claim citations, ReportSource inputs and the related Evidence panel.

**Acceptance boundary:** corpus claims cite actual in-scope sources; proposal generation/dismissal never changes research artifacts; acceptance rechecks permissions, source liveness and stale edits; repeated saves do not duplicate artifacts. New conversational workflows follow the existing REST-only classification while existing MCP report/search contracts stay in parity. WALK-3 passed these boundaries on the deployed build; its receipt preserves the first harness/configuration failures and the corrected checks.

**Outside this sprint:** password recovery is Sprint 61; sharing stays deferred, invites remain Derek's, and there is no RBAC redesign or autonomous writing. Twenty-one existing maintenance entries plus CI-documentation follow-up #464 were carried to the next backlog without expanding AUTH-1/AUTH-2. Next-step #405 is closed for the artifact choice and durable citation foundation only; historical gaps remain explicit. DeepSearch live-progress/runtime-identity follow-ups (#412/#416, message `1621f451`) were not resolved by this acceptance. Railway configuration follow-up #451 retains its recorded 2026-12-01 deadline.

### Follow-on — Sprint 61: Account recovery and live run logs (completed 2026-09-30)

All five missions shipped and passed their scoped deployed acceptance. The
[handoff](../planning/sprint-61-HANDOFF.md) preserves the approved plan;
the [WALK-4 receipt](../reports/sprint-61/WALK-4/README.md) records the final outcome.
CMOS is authoritative for status. Final TraceLab runtime merge is `4495119551c67a39b393b40f0e0d176ea84128ba`
(PR #406), and DeepSearch is `5a75502727b889aa4a65a6373df4b74aa36da23b`.

| Mission | Shipped outcome |
| --- | --- |
| **AUTH-1** | Public Resend recovery, single-use hashed token and account-scoped credential revocation; real email, reset, new login and old-password rejection accepted; sign-in copy corrected |
| **AUTH-2** | Admin/owner sends the same link to the stored mailbox with explicit target confirmation and secret-free audit; real delivered-link acceptance |
| **LOG-1** | Attempt-scoped v2 ingestion with ownership locks, stable identity, atomic replay and proof-free reads; PostgreSQL races, deployed synthetic proof and published MCP verified |
| **LOG-2** | Owned worker delivery during research, receipt freshness, retained errors and terminal refresh; actual preterminal browser acceptance followed by deployed legacy426 retirement |
| **WALK-4** | Expanded live credential revocation, unaffected main/service MCP, final serving build and receipt audit; closure and explicit maintenance carryovers |

The dedicated candidate completed the public and admin flows. Opening/requesting
the final link kept its JWT and ordinary/device keys valid; submitting the reset
revoked old JWT, refresh, query token, open stream, API/device keys and an approved
uncollected grant. The user confirmed a fresh login. The candidate remains active
as the user left it, with no temporary keys/grants. All seven other accounts retained
credentials; direct TraceLab and Aquex hub MCP both listed 65 projects. A separate
older Aquex connector's SSE404 is tracked independently. No main MCP credential changed.
Expiry/replay, legacy revision0 lifecycle, target denials and Settings behavior
are isolated regressions, distinguished from these production observations.

Exactly one authorized `S61-LOG2-ACCEPT-01` run produced two separately received
batches while in progress, a 10.627-second browser visibility upper bound and 12
retained final observations. Runtime hash `fa31cba8cf6f…` exactly matched the worker.
Research text, processed document, protocol-summary report and 24 Ledger entries
remain available. Controlled replay/transport-failure tests are not mislabeled
as production faults. #412 closes for this live evidence; #416 is accepted for
forward model/build identity only, with no historical repair.

All nine required CI checks passed: backend 3,074 passed / four skipped / 12
unchanged quarantined deselections; PostgreSQL 169 passed / two skipped; browser82
passed. The 190-test local retirement/cross-service run had no skips. The worker's
two known S87 baseline failures remain disclosed. Both themes at 390/820/1440,
keyboard/focus/axe, MCP parity and foundational checks passed their scoped tests.

The $5 allowance was planning guidance, not an enforced hard cap or billed amount.
Actual billed dollars are unavailable. Oversized research output, broad collection
and quality warnings are preserved for a separate follow-up; no paid rerun.
Twenty unrelated maintenance entries remain carried, including #451's 2026-12-01
deadline. DeepSearch's model evaluation, provider configuration and other paid work
were not changed. Sprint identity, decision ownership and CMOS parity are checked
at close; the historical receipts now identify resolved operator instructions.

### Follow-on — Sprint 62: Reliable operations and guided mission creation (Completed 2026-10-01)

The nine planned missions and user-requested CSV contrast addendum are accepted.
Decision **#576** and the [Sprint 62 handoff](../planning/sprint-62-HANDOFF.md)
record the scope; [final acceptance](../reports/sprint-62/S62-WALK/final-acceptance.json)
records the measured outcome. PRs [#408](https://github.com/kneelinghorse/TraceLab/pull/408),
[#409](https://github.com/kneelinghorse/TraceLab/pull/409) and
[#410](https://github.com/kneelinghorse/TraceLab/pull/410) merged; both services
served `d7b8682` for the final real-provider acceptance.

| Mission | Accepted outcome |
| --- | --- |
| **S62-ISO** | Pre-import provider isolation, in-memory cache fidelity, and explicit disposable Qdrant/PostgreSQL proof |
| **S62-CI** | Controlled backend deadline/cleanup diagnostics, exact activity-write smoke rules, unchanged twelve-test quarantine |
| **S62-MAIL** | One approved hello test email forwarded once; provider delivery and user-observed inbox Reply-To matched; Stage1 regressions retained |
| **S62-SCOPE** | Saved-run scope diagnosis completed; P1 DeepSearch correction remains open as **#479**, with exact evidence/fixture requirements |
| **S62-ENTRY** | Home/Missions/palette open focused planning; explicit inline project creation and reviewed draft save; manual/seed/repeat/general paths retained |
| **S62-OBS** | Legacy metrics failure repaired; bounded safe cache diagnostics distinguish outages from healthy zero; real isolated cache write/replay verified |
| **S62-UX** | Disabled sessions clear private state across transports; overflowing code is keyboard accessible |
| **S62-DEPLOY** | Named Railway partial owns only the two TraceLab services; effective runtime behavior, migration startup and eight unrelated resources preserved |
| **S62-CONTRAST** | Export CSV inherits readable foreground; four live theme/width checks and authenticated CSV download passed |
| **S62-WALK** | Real zero-project member planned with GPT-5.1, created a personal project, reviewed/saved one draft without dispatch, then passed disabled-session recovery and cleanup |

The first three real-provider attempts failed with `429 insufficient_quota`.
User-added credits resolved **#480** without changing model or provider. Subsequent
long replies exposed missing explicit transcript keyboard focus; the narrow fix
passed twelve real-local-API browser cases in Light/Dark at 390/820/1440 and the
complete deployed journey. Keep **GPT-5.1** for this release (decision **#585**).
Long link-free response fixtures and visible focus are now required regression
coverage (learning **#288**).

All nine required checks passed on the shipped source: backend **3,122 passed,
four skipped, twelve unchanged deselections**; PostgreSQL **169 passed, three
skipped**; frontend **368 unit tests** and **82 production browser checks**.
The final live run had zero draft lint errors, serious/critical axe findings or
page overflow. It saved exactly one draft and dispatched no research. Existing
192 broad-route, six S61 log-page and four live CSV checks remain applicable;
22 of 23 prior hashes are unchanged, with the changed Librarian source explicitly
retested. All 60 source-path citations are accounted for. The legacy CMOS runner
still has two independently verified baseline failures, which are not claimed green.

All ten promoted follow-ups **#397/#426/#444/#445/#446/#447/#451/#464/#476/#478**
and quota successor **#480** are resolved. **Fourteen remain open**: the thirteen
untouched carryovers plus P1 scope correction **#479**. The scope diagnosis does
not claim worker enforcement is fixed, and the historical empty-cache cause is
still unknown. Aquex owns its separate site-contact change; its completion
summary is ready but unsent. No additional mail, worker changes or paid research
were performed.

### Follow-on — Sprint 63: Clear onboarding and focused maintenance (Planned 2026-10-01)

Derek approved the post-S62 maintenance recommendation and requested a locked
handoff for a fresh build session. Decision **#589** and the
[Sprint 63 handoff](../planning/sprint-63-HANDOFF.md) define the scope; CMOS holds
the detailed acceptance criteria. Three missions are **Queued**, with no build
start/end dates yet:

| Mission | Planned outcome | Requires |
| --- | --- | --- |
| **S63-PUBLIC** | Accurate package license/version/tool guidance, first-run and empty-account path, factual repository description; documentation patch prepared | — |
| **S63-CLEAN** | Remove unused saved-search preset inputs while preserving the working save flow; correct affected frontend route/palette documentation | — |
| **S63-RELEASE** | Verify the published npm artifact, public metadata and frontend delivery; close accepted carryovers and record the outcome | PUBLIC, CLEAN |

The package is currently 2.1.0, with source matching its release tag; target a
2.1.1 documentation patch after a fresh registry/source check. The existing MIT
license applies to the adapter; this sprint does not select a service-wide license.
Preserve the retired mission-queue 404 tombstone and the save form's internal
draft snapshot. Acceptance includes the clean registry install required by DoD-1.

Existing **#449/#450/#481** are assigned to S63 and stay open until acceptance.
The other twelve rows remain outside, including P1 DeepSearch scope correction
**#479**, whose worker fixture must precede TraceLab vendor parity. Sharing remains
deferred. Aquex's hello forwarding is already accepted; its completion reply is
prepared but unsent. Planning performs no implementation, release, deployment,
public metadata write, cross-project message or paid research.

### Running alongside: the guest expansion track

> "tracelab has a few friends i've given access to but i think i want to expand that, so it will be for other software design pros to try it out."

Not a sprint of its own; a gate on the others. WALK-2 passed on 2026-09-22 (decision #531); invites go out when PERSONAL-1 ships (decision #530: personal Spaces before people come in), and it shipped on 2026-09-22; Derek now sends invites himself, on no timetable (decision #535). WALK-1 has been walked and METER-0 is recording; sharing is no longer the gate, though until it ships a guest cannot share their own work without an admin.

---

## Questions Answered (2026-09-18)

All three of the opening questions were answered in one pass. Kept here with their answers rather than deleted, because two of them changed the plan.

1. **Can two guests share a seeded reference corpus?** — **Answered: they should be able to, and today they cannot.** Derek's model is project-level sharing, owner-administered, with view/edit grants. That does not exist; sharing is Space-level and admin-only. This became Sprint 58 (decision #514), and the blast-radius warning became a requirement of it (decision #516).
2. **Does the Librarian ever write without asking?** — **Answered: never.** Permanently, not as a staging decision. Auto-jobs are suggestion-shaped only (decision #515). This simplified Sprint 60 considerably.
3. **How far does "synthesize or summarize" go before it becomes Q&A?** — **Answered: the question dissolved.** Derek struck the no-chat constraint, so there is no line to police; the Librarian converses freely and Q&A is a headline capability (decision #513). The dividing line that replaced it is provenance, not turn-shape.

## Open Questions for Derek

Add to this list rather than resolving items silently.

1. **Should project grants be genuinely per-project, or sugar over Space membership?** The agent recommends genuinely per-project, so the Space blast-radius warning is only shown when a Space grant is what the user actually chose. Not yet ruled on. **Deferred:** decision #526 moved sharing beyond Sprint 58, and Derek excluded it from Sprint 59 (decision #538: "don't care, no"). Revisit when he wants sharing; it is not an invitation gate or committed Sprint 60 work.
2. **Does `rag_default_max_tokens` stay a single default or become per-request?** A one-line answer and a full synthesis want different budgets. Sprint 59. **Answered: per request**, in the Sprint 59 plan Derek approved (decision #538), and built by QA-1 on 2026-09-23.

---

## Key Design Principles

1. **Artifacts are the point, not the gate.** The Librarian converses freely; turning a conversation into a mission, report or collection is always one action away (decision #513, superseding #511).
2. **Provenance over cleanliness.** A marked machine-written field beats a tidy corpus you cannot audit.
3. **Nothing writes unasked.** The Librarian acts only when asked, with a given prompt or context. No cron writes ad hoc; auto-jobs suggest and a human accepts (decision #515).
3. **Citations are not decoration.** If it cannot be cited, it is not asserted about the corpus.
4. **The agent acts as its user.** Never a service role. A user must not reach anything through the Librarian that they cannot reach directly.
5. **Cold start is a feature surface, not an error state.** The empty Space is where the funnel starts.
6. **Record now what you cannot reconstruct later.** Usage and provenance both.
7. **Missions cite human-authored warrants.** Decision #508: an agent-authored next-step, decision or commit body is context, never a mandate.

---

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| The Librarian becomes a worse general chat agent that happens to have your documents | Artifacts stay one action away at every turn; the corpus and tools are the reason to be there (decision #513) |
| Provenance blurs now that world knowledge and corpus claims share one reply | Rule 2, mutation-tested both ways: a fabricated citation fails, an uncited corpus claim fails |
| Someone shares a project and unknowingly grants access to a whole Space | The blast radius is shown in the sharing flow, not documented elsewhere (decision #516) |
| Auto-writes corrupt a corpus Derek cares about | Ruled out at the source: nothing writes without a human accepting it (decision #515) |
| A grounded answer that quietly is not grounded | Mutation test: a fabricated citation must fail |
| Guests hit a path nobody has walked | WALK-1, before invites |
| A guest cannot share their own work without an admin | Sharing remains deferred; personal Spaces shipped and invitations are Derek's choice (decisions #535, #538) |
| Guest cost becomes an open tab | METER-0 records now; policy later, with data |
| Building on unverified retrieval | RAG-1 gates the Q&A sprint, not the arc |
| The LLM framework space moves under us | LIB-0 runs first and is re-run if the arc extends past Sprint 60 |
| Inventing scope again | Every mission carries Derek's verbatim words (decision #508) |

---

## Terminology

- **Librarian** — the agent surface that operates TraceLab's tools on a user's behalf. It also converses like any other chat agent (decision #513); what distinguishes it is the corpus, the tools, and cited provenance.
- **Artifact** — a mission, report, collection, synthesis or document that persists in TraceLab.
- **Corpus claim** — a statement about what TraceLab holds. Always requires a citation.
- **Planning output** — a suggestion, question or framing. Uses world knowledge freely; asserts nothing about the corpus.
- **Guest** — a design pro invited to try TraceLab, in their own Space.

---

## Change Log

- **2026-10-01 UTC, Sprint 63 planning locked.** Decision #589: three Queued missions for package onboarding/metadata, confirmed frontend cleanup and release acceptance. Selected carry-forwards #449/#450/#481 remain open; twelve others retain their ownership. Fresh build begins from `codex/sprint-63-plan`, based on S62 closeout receipts `9caa93b`; no implementation started.

- **2026-10-01 UTC, Sprint 62 completed.** Ten of ten outcomes verified on `d7b8682`; real GPT-5.1 first-use passed after user-added credits and the narrow transcript keyboard fix. Mail/CSV accepted, #480 resolved, fourteen precisely scoped carryovers remain. See S62-WALK final acceptance.

- **2026-10-01 UTC, Sprint 62 acceptance follow-up; still Active.** PR #409 deployed as `e276977`, with the requested CSV label correction and live HTML/CSV checks passing. MAIL and #478 closed after the single approved forward and user-observed matching inbox Reply-To. Nine of ten missions are accepted; WALK is Blocked on existing provider quota (#480), reconfirmed by the cleaned-up third fixture attempt. No further mail, paid research, provider changes or cross-project reply.
- **2026-10-01 UTC, Sprint 62 build checkpoint; still Active.** Seven missions complete, PR #408 deployed as `4317a75`, all required source CI green with existing skips/quarantine disclosed. Scoped Railway migration and live cache diagnostics accepted; 192 broad UI checks and six S61 log-page checks passed. MAIL awaits authorized send and actual inbox/Reply-To proof; WALK awaits MAIL and a real first-use rerun after provider quota is restored. The P1 DeepSearch correction remains separately owned as #479. No sprint closure, email or cross-project reply claimed.
- **2026-09-30 UTC, Sprint 62 opened.** S62-ISO started in an isolated build worktree from `2d353e6`; CMOS identity and sprint pointers synchronized. Mandatory delivery and deployed acceptance gates remain open.
- **2026-09-30 UTC, Sprint 62 locked for fresh build (decision #576).** Nine Queued missions cover test isolation, CI diagnostics, hello forwarding, saved-run scope diagnosis, guided mission entry, cache observability, two narrow UX defects, supported Railway configuration and final acceptance. Ten existing follow-ups promoted; thirteen remain outside scope. Official Railway cutoff corroborated in Evidence Ledger; no runtime/deploy/mail/paid-run action. [Build handoff](../planning/sprint-62-HANDOFF.md).

- **2026-09-30 UTC, Sprint 61 detailed for a fresh build (decision #563).** Refined AUTH-1/AUTH-2 and added LOG-1, LOG-2 and WALK-4 in CMOS. Source inspection found missing session revocation/public-route/mail-secrecy work for recovery and intentional terminal-only delivery plus an unfenced append receiver for logs. The handoff preserves lease safety, replay semantics, independent recovery delivery, real mailbox/pre-terminal acceptance and the DeepSearch deployment boundary. Sprint remains Planned; no runtime or production actions performed.

- **2026-09-30 UTC, Sprint 60 closed six of six; the Librarian arc accepted.** WALK-3 used a dedicated temporary member for real planning, draft creation, descriptions/undo, duplicate review, edited collection save, cited report review/save/export, Q&A/refusal and chunk search. Published MCP 2.1.0, 30 deployed theme/viewport pages, scope/stale/revoked-source negatives and exact artifact retries passed. The account/key were disabled/revoked. All current required CI and exact serving-version checks passed; the receipt distinguishes initial harness failures, unchanged skips/quarantine and agent acceptance from Derek personally walking. Five earlier receipts and decision mechanisms were reverified; #405 closed within REPORT-1's boundary. Twenty-one existing maintenance entries and new CI-documentation follow-up #464 carried without starting Sprint 61. CMOS identity and its approved master-context mirror were synchronized. [Acceptance receipt](../reports/sprint-60/WALK-3/README.md).

- **2026-09-30 UTC, ORG-1 deployed and verified.** [PR #395](https://github.com/kneelinghorse/TraceLab/pull/395), serving `25e3acd`, adds reviewed excerpt groups, independent acceptance, durable retry receipts, source rechecks, provenance and explicit member ordering. Migration 055, PostgreSQL concurrency, intent mutations and all required code CI passed with skips disclosed. Real owner-account acceptance created one edited two-member collection from synthetic feedback; browser, export and published MCP retrieval preserved its order and source identities. Original project/source hashes and duplicate review remained unchanged. The frontend build passed but image export exceeded the first deployment wait; the later exact-version check and post-deploy rerun passed. [Receipt](../reports/sprint-60/ORG-1/README.md). This is agent verification; non-privileged end-to-end acceptance remains WALK-3. LIB-4 follows next.

- **2026-09-29 UTC, LIB-3 deployed and verified.** [PR #391](https://github.com/kneelinghorse/TraceLab/pull/391), serving commit `4d64190`, adds editable project-description drafts, signed caller/project/source-bound acceptance, retained provenance and guarded one-level restore. PostgreSQL migration/concurrency tests and mutation proofs passed; all required CI gates passed with existing skips disclosed in the [receipt](../reports/sprint-60/LIB-3/README.md). Live empty/populated projects proved draft-no-write, idempotent acceptance and exact restore; Light/mobile and Dark/desktop opened all seven source chunks by keyboard. Original descriptions were restored. This is agent verification, not Derek's personal acceptance. DUP-1 follows in a fresh session; four missions and the arc acceptance remain open.

- **2026-09-29 UTC, REPORT-1 deployed and verified.** [PR #389](https://github.com/kneelinghorse/TraceLab/pull/389), serving commit `93d71fc`, adds durable validated citation maps, scoped reads and export destinations. Both writers, legacy gaps, source revocation/deletion and cache identity are covered by regressions; PostgreSQL and mutation checks passed. Published MCP 2.1.0 created one report, reopened it and preserved all three citations through every export; deployed Light/mobile and Dark/desktop opened every exact chunk. [Receipt](../reports/sprint-60/REPORT-1/README.md) discloses CI skips and quarantine. LIB-3 follows in a fresh session; the arc remains open.

- **2026-09-29 UTC, Sprint 60 opened (REPORT-1).** Build session PS-2026-09-29-003 started the citation foundation in dependency order; identity pointers synchronized. Decision #552 records the additive persistence and scoped-read contract before implementation.

- **2026-09-29 UTC, Sprint 60 planned for build handoff (decision #551).** On Derek's explicit request to finish the Librarian arc, six missions were queued in CMOS: REPORT-1 → LIB-3 → DUP-1 → ORG-1 → LIB-4 → WALK-3. He chose one selected project for organisation and duplicate suggestions. Source inspection found report detail drops citations and synthesis loses marker identity, so durable report citations lead the sprint. Report remains the saved artifact, result Documents remain sources, and historical gaps are not disguised as valid support. The handoff records the carried-item dispositions, deployed acceptance and fresh-session start; no feature was implemented during planning.

- **2026-09-29 UTC, roadmap and inbox review; account recovery backlogged (decision #550).** TraceLab has no pending inbox messages; the request for DeepSearch logs during a run (`1621f451`) still awaits a response. Sprint 60 remains a Planned shell for the four remaining Librarian capabilities, with no missions started. Derek's password-recovery request is captured in Planned Sprint 61 as AUTH-1 (self-service through Resend) and AUTH-2 (admin-triggered reset link, Requires AUTH-1). The existing Settings form requires the current password and does not cover recovery. The roadmap now reflects the later sharing deferral rather than the superseded invitation gate. No runtime changes were made.

- **2026-09-17 UTC, created at Sprint 57 open.** Written from the Sprint 56 review conversation with Derek, which closed the RBAC arc and opened this one. Sprint 57 created in CMOS with five missions (LIB-0, LIB-1 *Requires LIB-0*, WALK-1, METER-0, RAG-1) and zero RBAC missions. The two rules were settled in that conversation: the artifact rule from Derek's "not a backdoor way for someone to have a chat account", and the claim-type boundary after Derek rejected the agent's proposed corpus-only bound on cold-start grounds. The agent's original sequencing — corpus Q&A first, retrieval as the gate for the whole arc — was wrong and was changed: authoring ships first because it works on day one and causes the corpus to exist, and RAG-1 gates the Q&A sprint only. Production baseline recorded above, including three facts that shaped the plan: no one but Derek has ever run a mission, a project lives in exactly one Space, and missions record no cost.

_Truth in data, evidence as the connective tissue, one system._
- **2026-09-18 UTC, Derek answered all three opening questions and two of them changed the plan.** (1) Rule 1 AMENDED: he struck his own no-backdoor-chat constraint, so the Librarian converses freely and Q&A is a headline capability rather than something to work up to (decision #513, superseding #511). LIB-1's criterion 3 was inverted accordingly — it had required a test proving a general question gets no conversational answer. Rule 2 is unchanged but now load-bearing, since provenance display is the only thing separating world knowledge from corpus claims inside one reply. (2) SHARING MOVED INTO SPRINT 58, displacing the writes sprint, after his description of project-level owner-administered sharing was checked against the tree and found not to exist at all — no `project_members`, no such control, sharing is Space-level and admin-only, so a guest cannot share their own work without Derek (decision #514). This is decision #196's deferred `resource_grants` phase being called up, not a reversal. At Derek's request the Space blast radius must be shown in the sharing flow itself (decision #516). (3) NO AUTONOMOUS WRITES, EVER (decision #515) — suggestion-shaped auto-jobs are the destination, not a stage, which collapsed the old Sprint 58 into Sprint 60. Also settled: search is absorbed into the Librarian rather than retired, keeping chunk rendering and leaving the service and MCP surface untouched, and the truncation Derek noticed is `rag_default_max_tokens = 350` at `app/core/config.py:50` with the frontend never sending an override.
- **2026-09-22 UTC, LIB-0 closed and LIB-1 shipped; Sprint 58 shell created.** LIB-0's run was verified against production and closed (decision #517 stands). LIB-1 shipped as PRs #349 and #350 with its design recorded first (decision #519) and its production acceptance recorded on the mission: the deployed Librarian authored `TRACE-SHARE-58` from a two-turn conversation about project-level sharing, and the mission ran unmodified to a 41-reference report, which Sprint 58 planning now starts from. The first production run also found and fixed a truncated-reply rendering defect (learning #236). The Flash-versus-Luna model question was closed as inconclusive with DeepSeek Flash retained and the Librarian's model made a configuration seam (decision #518). The 69 open next-steps were triaged (decision #520) and `sprint-58` exists as a Planned shell so carried items have a target; its missions are scoped at open with Derek's words.
- **2026-09-22 UTC, later the same day: METER-0 shipped and RAG-1 done; three of five Sprint 57 missions complete.** METER-0 landed as two PRs after its own production backfill exposed two mistakes unit tests could not (learning #237); production now holds 440 usage rows, none inconsistent, and the admin summary answers the per-user question by the runs' own dates. RAG-1 named its root cause (decision #523: a dead constructor seam since B21.8) and repaired the test with a mutation proof; the citation defect it surfaced was confirmed against production and is recorded as a next-step for the Q&A sprint rather than folded in. Derek's answers on the Librarian boundary, keys and DeepSearch logs are decision #521; the plain mission-create routes now authorize the project (PR #352). WALK-1 remains, and needs Derek live.
- **2026-09-22 UTC, evening: WALK-1 walked; all five Sprint 57 missions complete.** Derek ran the guest path live as a non-privileged account from an empty project to a completed DeepSearch run, the first production mission not his own. Eight findings recorded with evidence and his verbatim words (receipt `cmos/reports/sprint-57/WALK-1-guest-walk/`); his verdict: "overall, very impressed so far" and "a really great first version". The Librarian findings became LIB-2 in Sprint 58 under decision #525, which also fixes the two-step create-then-submit as intentional ("a draft ... can be run at anytime"). Two diagnoses were corrected against the database rather than accepted as reported: the missing in-progress feed is DeepSearch batching its logs after completion, not a credential gap (learning #238, message `1621f451`), and the "translated evidence" is a small share of natively foreign-language sources. The guest account was disabled after the walk.
- **2026-09-22 UTC, Sprint 57 closed five of five; Sprint 58 re-scoped from sharing to good working order (decision #526).** Derek at close: "i'm not sure what sharing firts means, i want it to be in good working order before i bring people in, so lets proceed with the adjustments we just discussed and i'll rewalk it and go from there." Sprint 58 opened 2026-09-22 with LIB-2, GUEST-1, BADGE-1 and WALK-2, each traced to a WALK-1 finding; the sharing analysis is kept below the sprint as deferred, to be re-sequenced after the rewalk. The invite gate moved from "Sprint 58 has shipped" to "WALK-2 passes".
- **2026-09-22 UTC, later: LIB-2 shipped, the first Sprint 58 mission, hours after the walk that produced it.** PR #358 merged as `ff0dc98` and deployed; the deployed bundle was checked read-only (a stored conversation renders on load, the strip dismissal survives a reload) and the /librarian baseline was captured in both themes at 1440 and 390 with no failures, closing next-step #409. LIB-2's acceptance is WALK-2, by design. GUEST-1 and BADGE-1 wait on two one-line rules from Derek.
- **2026-09-22 UTC, evening: GUEST-1 and BADGE-1 shipped; three of four Sprint 58 missions complete on the day the sprint opened.** Both rules came from Derek in one line each (decision #528) and were built inside them (#529). Verified in production as the guest account: a guest's project lands in the Walkthrough Guest Space while Derek's still lands in Default, and one call cleared the 296-entry run's badge. WALK-2 is the only open mission; it needs Derek live on the deployed build.
- **2026-09-22 UTC, night: WALK-2 closed on Derek's rewalk; Sprint 58 gains PERSONAL-1 and PERSONAL-2 (decisions #530, #531).** Derek rewalked unwatched as the guest on `3f2dd9c`; the run completed with 243 ledger entries and his verdict was "walk is done, close it out. its fine for now." The rewalk did not exercise GUEST-1's placement (he reused the WALK-1 project) or BADGE-1's clear (no evidence view for the new run); both stand on their own production receipt. DeepSearch logs still arrive as one batch after completion (#412 open). The Space model then took the Google Drive shape in a dedicated planning session: a personal Space per user, created with the account, new projects defaulting there, Derek-Private designated as Derek's, Default Workspace left as his legacy bucket, and shared-Space creation as a second mission. Six scoping questions were put to Derek and answered in one line each (decision #531). Nothing is built; a fresh build session starts PERSONAL-1 on Derek's hand-off.
- **2026-09-22 UTC, late night: PERSONAL-1 shipped; Sprint 58 is five of six.** Built in a fresh build session on Derek's hand-off, with the placement rule recorded before code (decision #532, superseding the GUEST-1 halves of #528 and #529). Migration 052 gave every human a personal Space: Derek-Private is designated as Derek's, and the other seven are new. The guest's project moved out of Default with its children, and nothing privileged moved. Verified in production as the guest and as Derek through the MCP credential; the guest was disabled afterwards. The production baseline caught one regression the tests could not, project names squeezed at 390px by the longer Space labels, and PR #364 (`fe4c112`) fixed it the same night. PERSONAL-2 (creating inside a shared Space) is the one open mission.
- **2026-09-23 UTC, just after midnight: PERSONAL-2 shipped; all six Sprint 58 missions are complete.** Built in its own session straight after PERSONAL-1, as planned ("two session vs 1"), with the design recorded first (decision #533). A member now picks which of their Spaces a new project lives in, and the choice is checked against membership for the UI, the Librarian and the MCP alike. The full local run of CI's backend invocation caught a missed OODS contract mapping before merge (learning #210's rule), and the 200 ms graph gate started failing on a garbage-collection pause (four failures in under an hour, one on a docs-only commit), so PR #367 (`9f1b11b`) now times the graph layer with collection off, as timeit does. Verified in production through the real picker with a second member seeing the project. Sprint 58 is ready to close; the invite gate reading waits on Derek (next-step #432).
- **2026-09-23 UTC: Sprint 58 closed, six of six.** The receipt re-verification runbook (decision #509) found one stale citation: the GUEST-1 receipt's sole-Space mechanism, removed by PERSONAL-1. It was annotated in place, and decisions #528 and #529 were superseded by #534, which restates their still-valid BADGE-1 halves. Every open next-step was carried to a Sprint 59 shell, whose missions are scoped with Derek. The project identity reads `sprint-58-complete` and `cmos/context/MASTER_CONTEXT.json` was regenerated. Open for Derek: whether PERSONAL-1 shipping opens the invite gate (#432).
- **2026-09-23 UTC, Derek's answers at the handoff (decision #535).** Invites are his to send, with no timetable, and no longer a gate agents track. The MCP is to be updated: @aquex/tracelab-mcp 2.0.0 (mission MCP-5) carries ACT-1's removals and PERSONAL-2's workspace_id, and Derek publishes it with his one-time code. The Librarian stays off the MCP by LIB-1's classification. Owners and admins seeing every Space in the picker is "fine for now"; a super-admin tier is his to raise. The legacy kneelinghorse@tracelab.local account is renamed "kneelinghorse (legacy)" so the admin list no longer shows two "kneelinghorse" Spaces.
- **2026-09-23 UTC: @aquex/tracelab-mcp 2.0.0 published; MCP-6 joins Sprint 59.** Derek published at 02:28:51Z, and npm's shasum matched the agent's dry run (`591313b7…`, 24 files). Installed fresh with `npx`, the package passed 15 of 15 end-to-end checks against production: 9 tools, 49 actions, the ACT-1 and PERSONAL-2 surfaces, read-only calls and 27 resolving links. Corpus Q&A over the MCP is filed as MCP-6 in Sprint 59 (decision #536).
- **2026-09-23 UTC: Sprint 59 mid-sprint review, day one (session PS-2026-09-23-002).** MCP-5's start had activated the Sprint 59 shell at 01:59:36Z while the project identity still read `sprint-58-complete`; the review synced it to `sprint-59-active`, condensed the master context from 77.4 to 72 KB and regenerated the export. Checking this document's claims against the tree found one stale: PR #348 raised `rag_default_max_tokens` to 1500 on 2026-09-18 and the Sprint 59 section and next-step #401 still said 350 (learning #246); corrected above, with the per-request question left open for Derek. Every MCP-5 claim verified: npm's shasum and file count equal the dry run, the tag sits on `a5c882b`, all eight main-push runs on `a287ead` are green and both Railway services serve it. The Q&A planning session with Derek remains the sprint's real open: an end date, the Q&A missions with the citation fix (#417) first, MCP-6's cluster and shape, and the re-sequencing of sharing (#526) now that the rewalk has passed; the thirteen carried next-steps all show a lapsing lease and are re-carried before any close.
- **2026-09-23 UTC: Sprint 59 planned on Derek's hand-off (decision #538).** "create the sprint and missions in cmos so that we can hand this off to a fresh agent session and get this set of work done." Four missions filed in build order with Requires edges: RAG-2 (citations that resolve, or nothing), QA-1 (ask the Librarian a question about the research), QA-2 (search absorbed into the Librarian), MCP-6 (the same Q&A over the MCP, 2.1.0); each in its own fresh build session, merged and deployed before the next. Sharing is out ("don't care, no"); invites stay his. End date 2026-10-07. The Sprint 59 section above is re-planned from the CMOS missions; the earlier review's five "questions" were ledger bookkeeping and are withdrawn.
- **2026-09-23 UTC: RAG-2 shipped; RAG-3 added ahead of QA-1.** PR #374 (`949c7a6`): the RAG pipeline no longer returns a citation that resolves to nothing (unmatched labels dropped, the top-chunk fallback removed), and when retrieval is empty it returns an explicit nothing-found result (`no_evidence: true`) without calling the model; each fix is mutation-proved. Production probes confirmed both, and found that search hands the model chunks with no text, because PEDR fusion keeps the graph layer's thin record over the semantic layer's full one. That is filed as RAG-3, first before QA-1. QA-1 inherits two findings: the Search page's answer budget is still 350 tokens (the request schema's own default overrides PR #348's raise), and the nothing-found flag covers empty retrieval only, so refusing an unsupported question needs its own rule.
- **2026-09-23 UTC: RAG-3 shipped; RAG-4 added ahead of QA-1.** PR #376 (`4d8257d`): PEDR fusion keeps every field any layer supplied for a chunk, so a chunk the graph ranks first keeps its text; a chunk without text never reaches the model, and if none has text the answer is the nothing-found result; an owner's or admin's project or document filter now holds on graph results. Each fix is mutation-proved. On production two new questions got real text and citations that open, and POST /pedr/search returned content on all ten results. Both answers still said the fact was not in the context: the graph layer demotes the best matches below their own neighbours, and compression's 0.7 cut lets one chunk through. That is filed as RAG-4, before QA-1. Also found: production's default answer budget is still 350, because a Railway variable overrides the code default PR #348 raised; corrected in this section and handed to QA-1.
- **2026-09-23 UTC: RAG-4 shipped; QA-1 is next.** PR #378 (`65b11ef`, decision #541): the graph layer ranks its seeds first, in retrieval order, so a chunk reached from a best match can no longer outrank it; the order is by position because lexical and semantic seed scores are on different scales. Compression's floor drops from 0.7 to 0.4, set from seven questions measured on production. Two T37.4 graph tests had passed only because of the defect (every rank change in their data was a seed's neighbour jumping to first) and now assert the new rule. Each fix is mutation-proved. On production the reworded PII question and a new Qdrant cost question each got their answering chunk into the top five and in front of the model, and the answers state the fact. For QA-1's refusal rule: an unsupported in-domain question peaked at 0.37 against 0.49–0.66 for supported ones.
- **2026-09-23 UTC: QA-1 shipped; QA-2 and MCP-6 are next.** PR #380 (`ccade35`, decision #543) and follow-up #381 (`b140085`). The Librarian answers a question about a project's documents through one Q&A service, which MCP-6 will share. Every citation opens its chunk, a question the project cannot support is refused, and the budget is chosen per request, which answers the second open question above. On production, three questions got cited answers that state their facts, every link opened, and the unsupported question was refused before the model. The first production run found two defects that tests had missed, both fixed in #381: a range citation left as raw text, and a long chunk's header scrolled off screen. Also found: two of QA-1's first tests reached production's Qdrant through the local `.env` (learning #256). The only effect was a payload index created a few hours before the deploy that creates it anyway.
- **2026-09-23 UTC: QA-2 shipped; MCP-6 is last.** PR #383 (`814c166`, decision #545). The standalone Search page is retired into the Librarian: "List the chunks" shows the ranked chunks for a phrase, each opening in its document, and the list saves as a collection. `/search` redirects to the Librarian with its query, and saved searches run there. Checked on production against the ALIAS-1 trap: nothing under `/search` serves a page, and the deployed build has no `/search` page. The receipt also fixes a Sprint 58 Librarian test that raced the draft panel's focus on cold runs. Two older gaps showed up in the full baseline and are left for later: the smoke harness doesn't suppress the Evidence page's mark-seen write, and one document's wide code blocks fail axe at 390 px.
- **2026-09-23 UTC: MCP-6 shipped and @aquex/tracelab-mcp 2.1.0 published; Sprint 59's last mission.** PR #385 (`0bff859`, decision #547). An agent using the MCP now asks a project a question through QA-1's one Q&A service, under the Librarian's citation rule and the caller's own access, and each citation opens its chunk. Derek published at 23:58:41Z, and the tarball the registry serves is byte-identical to the agent's dry run (`797087ef…`, 24 files). Installed fresh with `npx`, the package passed 19 of 19 end-to-end checks against production. Also found: Railway's CLI says `railway.json` keeps working only until 2026-12-01, and the backend's migrations run from the start command in that file, so it is on the ledger with its date.
- **2026-09-24 UTC: Sprint 59 closed, seven of seven.**
  - **MCP-6's receipt** (PR #386, `86ac8c6`) records that the 2.1.0 on npm is byte-identical to the agent's dry run and passed 19 of 19 on production.
  - **The receipt re-verification** (decision #509) checked every path and symbol cited in the seven receipts and in the sprint's decisions against HEAD. RAG-2's receipt described code that RAG-3 and RAG-4 later fixed, and cited lines that MCP-6's imports moved, so it now carries two correction notes. Every other citation holds.
  - **CMOS:** the project identity reads `sprint-59-complete`, `cmos/context/MASTER_CONTEXT.json` is regenerated, and a Sprint 60 shell holds the 23 carried next-steps. Its missions are Derek's to scope.
  - **The master context** is 78 KB of its 100 KB limit. Most of it is a rolling window of the last 40 session notes, so its size is bounded, and the manual prune planned for this close was not needed.
  - **The CMOS database** is 81 MB, all of it live data (65 MB is context snapshots), growing 1–2 MB a working day. The backfill upload fails above 100 MB, so pruning old snapshots after a backup, which cannot be undone, is Derek's call.

- **2026-09-30: Sprint 61 opened in build session PS-2026-09-30-005.** AUTH-1 started; decision #564 freezes recovery endpoints, migration 056, token replacement/failure rules and credential invalidation. Deployed acceptance remains a separate required gate.

- **2026-09-30: Sprint 61 completed, five of five.** Public/admin recovery and live log delivery accepted; final legacy retirement serves4495119. WALK-4 records candidate-only revocation, unaffected MCP, exact CI/serving evidence, #412/#416 dispositions and explicit carryovers. One paid run only; scope/quality warnings and unknown billed dollars retained.
