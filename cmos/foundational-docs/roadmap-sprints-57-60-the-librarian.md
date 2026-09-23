# TraceLab — Vision and Roadmap: The Librarian (Sprints 57–60)

**Status:** Living document. Authoritative for INTENT; CMOS is authoritative for STATUS.
**Opened:** 2026-09-17, at Sprint 57 planning.
**Predecessor:** `roadmap-sprints-50-53-ux-overhaul.md`, which carried Sprints 50–56 and is now closed to new sprint sections.

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

### Sprint 59 — Q&A, and the search question answered (opened 2026-09-23; planned the same day on Derek's hand-off; RAG-2 and RAG-3 shipped and RAG-4 added the same day)

Corpus Q&A, now a headline capability rather than something to work up to, since Rule 1 was amended. Gated on RAG-1 from Sprint 57: a Q&A surface over a retrieval path whose cited-answer test does not run makes every wrong answer ambiguous — bad retrieval or bad generation, unknowable.

**Search is absorbed, not retired.** Derek asked whether the two coexist:

> "Right now, our search page is not unlike a chat bot in some ways already in that it returns chunks but we call an LLM to synthesize the chunks and provide a response. I've notiece those responses get truncated... Probably good to have search remain for the mcp surface. so the service wouldn't go away but not sure about the UI."

Settled: the Librarian becomes the primary surface, and a **chunk list stays one of the things it can render** — scanning twenty chunks for a half-remembered quote is a genuinely different job from asking a question, and it is exactly the job the org case describes. A saved chunk list is a collection, which is an artifact. The `/search` service and its MCP surface are untouched. The standalone page retires in this sprint, not before — and mind the ALIAS-1 trap, where a sibling dynamic route kept answering 200 after the page was deleted.

**The truncation is diagnosed, and the default is raised.** `app/core/config.py:50` set `rag_default_max_tokens = 350` — roughly 260 words — and the frontend never sends `max_tokens`, so every synthesis used that hard default. Not a rendering or streaming bug; a config default nobody revisited. PR #348 (`4feb3e3`, 2026-09-18) raised it to 1500; this section and next-step #401 kept saying 350 until the 2026-09-23 review checked the claim against the tree. **In production it is still 350** (found by RAG-3, 2026-09-23): Railway sets `RAG_DEFAULT_MAX_TOKENS=350` on the TraceLab service, as `.env.example` does, and that overrides the code default, so the raise never reached a production answer. QA-1's per-request budget defaults to this setting and carries the fix. Open design point, Derek's: whether it stays a single default or becomes per-request, since a one-line answer and a full synthesis want different budgets.

**The plan (2026-09-23, decision #538).** Derek: "create the sprint and missions in cmos so that we can hand this off to a fresh agent session and get this set of work done." Four missions, filed in CMOS with Requires edges, in build order; each runs in its own fresh build session and is merged, deployed and verified in production before the next starts.

- **RAG-2 — Citations that resolve, or nothing.** The RAG pipeline stops inventing citations (labels that match no retrieved chunk are dropped, the top-chunk fallback goes) and short-circuits with an explicit nothing-found result when retrieval is empty; each fix carries a test proven by mutation. Replaces the RAG-1 escalation. First, because every answer below flows through this path. **Shipped 2026-09-23** (PR #374, `949c7a6`; receipt `cmos/reports/sprint-59/RAG-2/`): all three fixes, each mutation-proved, and `no_evidence` on the search response. Its production probes found that search hands the model chunks with no text, so RAG-3 was added ahead of QA-1.
- **RAG-3 — Retrieval keeps each chunk's text** (added 2026-09-23 from RAG-2's production finding). PEDR fusion keeps the whole record from whichever layer ranked a chunk best, and the graph layer's records carry no text, so every chunk the graph ranks above semantic reaches the model empty. On production a real question about TraceLab Research got five such chunks and the answer "no information". The fix repairs fusion, keeps chunks without text away from the model, applies an explicit project filter to graph results for every caller, and is accepted on production with a real question whose citations open. **Shipped 2026-09-23** (PR #376, `4d8257d`; receipt `cmos/reports/sprint-59/RAG-3/`): all three fixes, each mutation-proved. On production the model now reads real text (about 4,000 tokens where RAG-2 saw none), every citation opens at its chunk, and POST /pedr/search returns content on every result. The same probes found the model shown a neighbour of the chunk that answers, so RAG-4 was added ahead of QA-1.
- **RAG-4 — The model sees the chunks that answer the question** (added 2026-09-23 from RAG-3's production finding). Both of RAG-3's answers cited real text and still said the fact was not there. Graph expansion is seeded with the top ten matches and never ranks a seed itself, so the seeds' neighbours outrank them: the chunk that answers the PII question is first with the graph layer off and fifteenth with it on. And compression's 0.7 similarity cut sits above every similarity production produced (at most 0.66), so exactly one chunk reaches the model. The fix keeps the best matches in front and lets more than one relevant chunk through, accepted on production with a question whose answering chunk is known in advance and an answer that states the fact. QA-1 waits on it.
- **QA-1 — Ask the Librarian a question about the research.** One Q&A service function that is the only Q&A path; on the Librarian page an answer whose every citation opens a real chunk or evidence entry, corpus claims separated from world knowledge, refusal when the project cannot support the question, and an answer budget chosen per request (closing the single-default question above). Accepted on production against a real project.
- **QA-2 — Search absorbed into the Librarian.** A plain chunk list the Librarian can render and save as a collection; the standalone Search page retires with a redirect, checked on production against the ALIAS-1 trap; the `/search` service and the MCP search tool untouched.
- **MCP-6 — The same Q&A over the MCP.** `tracelab_search` gains an `ask` action over the shared service, same citation rule and access scope, with an MCP-client test proving cross-project denial; released as 2.1.0 by Derek's publish.

MCP-5 shipped @aquex/tracelab-mcp 2.0.0 on 2026-09-23 (decision #535; receipt `cmos/reports/sprint-59/MCP-5/`). **Out of the sprint:** sharing (Derek, 2026-09-23: "don't care, no"), invites (his, no timetable), everything else; the small leftovers stay on the ledger and are not raised with him unless he asks. End date 2026-10-07.

### Sprint 60 — Suggestions, and the org case (planned)

**Simplified 2026-09-18 by decision #515.** Derek ruled out autonomous writes permanently, not as a staging decision:

> "no librarian is always asked and always has a given prompt or context. No ad hoc writes from an auto or chron. auto jobs should only ever be low risk, or suggested, like drafting a mission idea. i would still need to run it or if we did de-duping for instance, it would be presenting those as options as to how to remediate."

So the suggestion queue is the **destination**, not a stepping stone, and the hard problem of making an unattended writer safe does not need solving at all. That collapses the old Sprint 58 into this one:

- Project descriptions drafted for a human to accept — *"eventually all projects have descriptions"*, one acceptance at a time.
- Duplicate detection that **presents remediation options**, never performs the merge.
- Organisation suggestions, and report assembly from existing chunks for the org case: *"help researchers pull out user feedback or summarize or create new reports from compilied chunks."*
- Provenance marking survives, demoted from safety mechanism to useful bookkeeping: knowing a description was Librarian-drafted and human-accepted is worth recording.

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

1. **Should project grants be genuinely per-project, or sugar over Space membership?** The agent recommends genuinely per-project, so the Space blast-radius warning is only shown when a Space grant is what the user actually chose, rather than living permanently on the sharing UI. Not yet ruled on. Sharing was deferred past Sprint 58 by decision #526, to be re-sequenced after the rewalk; the rewalk passed on 2026-09-22, so this is put to Derek at Sprint 59 planning.
2. **Does `rag_default_max_tokens` stay a single default or become per-request?** A one-line answer and a full synthesis want different budgets. Sprint 59.

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
| A guest cannot share their own work without an admin | Sprint 58 ships before any invitation goes out |
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
