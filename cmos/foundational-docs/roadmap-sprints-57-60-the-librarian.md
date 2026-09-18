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

### Sprint 57 — The Librarian, Part 1: Authoring (opened 2026-09-17, runs to 2026-10-01)

**Goal:** Ship the surface that works on day one for a user with no corpus, and find out what breaks when someone other than Derek uses the system.

Missions (CMOS is authoritative for status):

- **LIB-0 — Research the build, using TraceLab to decide how to build TraceLab.** A real DeepSearch mission on grounded tool-operating agents as of late 2026; its report becomes LIB-1's design reference. Deliberately dogfooded. Findings that change LIB-1's design are recorded as decisions *before* LIB-1 is built.
- **LIB-1 — The mission-authoring assistant.** Conversation in, a real DeepSearch mission out. World knowledge free for shaping the question, free conversation allowed, and the claim-type boundary enforced by test in both directions. Criteria rewritten 2026-09-18 under decision #513. *Requires LIB-0.*
- **WALK-1 — The guest path, walked.** Derek and the agent watch a mission run end to end from a fresh Space, as a new design pro would, ideally as a non-privileged principal. Supersedes next-steps #330 and #355, deferred across four sprints.
- **METER-0 — Record what a mission costs.** Data only. No quotas, no limits, no billing, no user-visible surface.
- **RAG-1 — Diagnose the skipped cited-answer test.** Root cause named, not worked around; explicitly not an SDK upgrade.

**Out of scope, deliberately:** any corpus Q&A surface, any automatic write to existing records, any RBAC mission, any metering policy.

### Sprint 58 — Sharing, as Derek means it (planned)

**Moved into this slot 2026-09-18 (decision #514), displacing the writes sprint, because every guest invitation is blocked on it.**

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

Not a sprint of its own; a gate on the others. Invites go out when WALK-1 has been walked, METER-0 is recording, and **Sprint 58 has shipped** — because until it does, a guest cannot share their own work without an admin.

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
