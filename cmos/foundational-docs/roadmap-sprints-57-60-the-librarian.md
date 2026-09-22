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

### Sprint 58 — Good working order: the WALK-1 adjustments and the rewalk (opened 2026-09-22, runs to 2026-10-06)

**Re-scoped at Sprint 57 close (decision #526).** The slot held sharing; Derek moved it: *"i'm not sure what sharing firts means, i want it to be in good working order before i bring people in, so lets proceed with the adjustments we just discussed and i'll rewalk it and go from there."*

**Goal:** Fix what the live guest walk found, then walk it again. Nothing new is designed; every mission traces to a WALK-1 finding and to Derek's decision on it.

Missions (CMOS is authoritative for status):

- **LIB-2 — Librarian orientation and persistence.** Findings 1, 3, 4, 5, 6 under decision #525: the transcript survives navigation, a successful draft is scrolled into view and announced, the mission page orients a user arriving from the Librarian (dismissable, remembered), the Draft button becomes the call to action when the model says there is enough, and the transcript gets room. The two-step create-then-submit stays exactly as it is; the colour meter is not built. **Shipped 2026-09-22** (PR #358, `ff0dc98`; decision #527): persistence in per-user localStorage with the server still stateless, focus and a toast after Draft, a three-step strip plus a `?from=librarian` notice behind one remembered dismissal, Draft as the primary button on the model's signal, a wider column and taller transcript with an Expand toggle. Verified on production by a read-only live check and a four-shot baseline with zero failures. Accepted when WALK-2 passes. Receipt: `cmos/reports/sprint-58/LIB-2-librarian-baseline/`.
- **GUEST-1 — A guest's new project lands in the guest's Space.** Finding 2: `default_workspace_id()` sends every new project to Default Workspace regardless of caller. The rule for members with one Space is decided with Derek's words and Derek's own creation path is unchanged unless he says otherwise.
- **BADGE-1 — The Evidence badge clears without paging through a run.** Finding 7: the badge is the activity new-count per entry and one run adds hundreds.
- **WALK-2 — The rewalk.** Derek walks the guest path again on the fixed build, ideally with the DeepSearch log flush landed so the Runner logs panel fills during the run (next-step #412). Invites are gated on this walk, not on sharing.

**Out of scope, deliberately:** project-level sharing (below, deferred), corpus Q&A, autonomous writes, RBAC missions, metering policy, the search-page citation fix (next-step #417, before Sprint 59).

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

### Sprint 59 — Q&A, and the search question answered (planned)

Corpus Q&A, now a headline capability rather than something to work up to, since Rule 1 was amended. Gated on RAG-1 from Sprint 57: a Q&A surface over a retrieval path whose cited-answer test does not run makes every wrong answer ambiguous — bad retrieval or bad generation, unknowable.

**Search is absorbed, not retired.** Derek asked whether the two coexist:

> "Right now, our search page is not unlike a chat bot in some ways already in that it returns chunks but we call an LLM to synthesize the chunks and provide a response. I've notiece those responses get truncated... Probably good to have search remain for the mcp surface. so the service wouldn't go away but not sure about the UI."

Settled: the Librarian becomes the primary surface, and a **chunk list stays one of the things it can render** — scanning twenty chunks for a half-remembered quote is a genuinely different job from asking a question, and it is exactly the job the org case describes. A saved chunk list is a collection, which is an artifact. The `/search` service and its MCP surface are untouched. The standalone page retires in this sprint, not before — and mind the ALIAS-1 trap, where a sibling dynamic route kept answering 200 after the page was deleted.

**The truncation is diagnosed.** `app/core/config.py:50` sets `rag_default_max_tokens = 350` — roughly 260 words — and the frontend never sends `max_tokens`, so every synthesis uses that hard default. Not a rendering or streaming bug; a config default nobody revisited. Open design point: whether it stays a single default or becomes per-request, since a one-line answer and a full synthesis want different budgets.

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

Not a sprint of its own; a gate on the others. Invites go out when WALK-2 passes on the fixed build (decision #526). WALK-1 has been walked and METER-0 is recording; sharing is no longer the gate, though until it ships a guest cannot share their own work without an admin.

---

## Questions Answered (2026-09-18)

All three of the opening questions were answered in one pass. Kept here with their answers rather than deleted, because two of them changed the plan.

1. **Can two guests share a seeded reference corpus?** — **Answered: they should be able to, and today they cannot.** Derek's model is project-level sharing, owner-administered, with view/edit grants. That does not exist; sharing is Space-level and admin-only. This became Sprint 58 (decision #514), and the blast-radius warning became a requirement of it (decision #516).
2. **Does the Librarian ever write without asking?** — **Answered: never.** Permanently, not as a staging decision. Auto-jobs are suggestion-shaped only (decision #515). This simplified Sprint 60 considerably.
3. **How far does "synthesize or summarize" go before it becomes Q&A?** — **Answered: the question dissolved.** Derek struck the no-chat constraint, so there is no line to police; the Librarian converses freely and Q&A is a headline capability (decision #513). The dividing line that replaced it is provenance, not turn-shape.

## Open Questions for Derek

Add to this list rather than resolving items silently.

1. **Should project grants be genuinely per-project, or sugar over Space membership?** The agent recommends genuinely per-project, so the Space blast-radius warning is only shown when a Space grant is what the user actually chose, rather than living permanently on the sharing UI. Not yet ruled on. Sprint 58.
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
