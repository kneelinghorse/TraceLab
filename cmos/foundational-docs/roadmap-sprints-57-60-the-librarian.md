# TraceLab — Vision and Roadmap: The Librarian (Sprints 57–60)

**Status:** Living document. Authoritative for INTENT; CMOS is authoritative for STATUS.
**Opened:** 2026-09-17, at Sprint 57 planning.
**Predecessor:** `roadmap-sprints-50-53-ux-overhaul.md`, which carried Sprints 50–56 and is now closed to new sprint sections.

Revisit this document at **every sprint open and every sprint close**, the same way its predecessor was maintained: at close, rewrite the closing sprint's section as outcome; at open, re-plan the opening sprint's section from the CMOS missions; append a dated line to the Change Log either way. A sprint is not closed while its section here still reads as a plan.

---

## Vision Statement

TraceLab already does the hard part: it runs real research, keeps the evidence, and lets you audit any claim back to its source. What it does not do is help you *ask*. Every mission today is hand-authored by someone who already knows how to author missions, and the only person who has ever run one is Derek.

The Librarian closes that gap. It is an agent that **operates TraceLab's existing machinery on a user's behalf** — authoring missions, synthesising research, assembling reports from chunks the system already holds. It is not a chat product with documents attached. The difference is not cosmetic: it is what keeps the evidence ledger the point of the system rather than decoration.

> "using the exising tools to do work" — Derek, 2026-09-17

---

## The two rules this arc is built on

Everything below follows from two constraints. Both came out of the Sprint 56 review conversation, and both are cheap now and expensive to retrofit.

### Rule 1 — The artifact rule

**Every Librarian turn ends in a TraceLab artifact, or it ends in nothing.** A mission authored, a report drafted, a collection assembled, a synthesis saved. A turn that ends in only a reply is chat, and chat is out of scope.

This comes directly from Derek's anti-goal: *"i'm not trying to make it a backdoor way for someone to have a chat account."* It replaces a usage policy with a design property, and it is testable — a general-knowledge question must not receive a conversational answer.

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

**A project lives in exactly one Space.** `projects.workspace_id` is a single FK and zero projects are unassigned. Two guests cannot share a seeded reference corpus without duplicating the project or placing them in the same Space. This constrains the invite plan and is unresolved.

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
- **LIB-1 — The mission-authoring assistant.** Conversation in, a real DeepSearch mission out. World knowledge free for shaping the question; the artifact rule and the claim-type boundary both enforced by test. *Requires LIB-0.*
- **WALK-1 — The guest path, walked.** Derek and the agent watch a mission run end to end from a fresh Space, as a new design pro would, ideally as a non-privileged principal. Supersedes next-steps #330 and #355, deferred across four sprints.
- **METER-0 — Record what a mission costs.** Data only. No quotas, no limits, no billing, no user-visible surface.
- **RAG-1 — Diagnose the skipped cited-answer test.** Root cause named, not worked around; explicitly not an SDK upgrade.

**Out of scope, deliberately:** any corpus Q&A surface, any automatic write to existing records, any RBAC mission, any metering policy.

### Sprint 58 — Writes, with provenance (planned)

The auto-jobs Derek described:

> "the auto jobs would be things like adding project descriptions based on the content of the project so that eventually all projects have descriptions. we could do things like look for dupes or make suggestions for better organization?"

These are the easiest thing in the arc to ship and the most dangerous, because they write into a corpus that matters. The sprint's shape is therefore **provenance first, writes second**:

- Machine-authored fields are marked as such, durably, at write time.
- Every machine write is revertable in one action.
- Auto-jobs ship as **suggestions a user accepts**, not jobs that mutate.
- First application: project descriptions, because 59 wrong descriptions with no way to tell which were machine-written is the exact failure this ordering prevents.

### Sprint 59 — Corpus Q&A, grounded (planned)

The chapter Derek wants to *work up to*. Gated on RAG-1: a Q&A surface over a retrieval path whose cited-answer test does not run makes every wrong answer ambiguous — bad retrieval or bad generation, unknowable.

Rule 2 does the heavy lifting here. Every corpus claim carries a resolving citation; a fabricated citation fails a test.

### Sprint 60 — Organisation intelligence and the org case (planned)

> "Eventually the idea would be that this would be used in an org and it could help researchers pull out user feedback or summarize or create new reports from compilied chunks etc."

Duplicate detection, organisation suggestions, and report assembly from existing chunks. All artifact-producing, all operating existing tools. Sequenced last because each one is a write against a corpus, and it inherits Sprint 58's provenance model.

### Running alongside: the guest expansion track

> "tracelab has a few friends i've given access to but i think i want to expand that, so it will be for other software design pros to try it out."

Not a sprint of its own; a gate on the others. Invites go out when WALK-1 has been walked, METER-0 is recording, and the one-project-one-Space constraint has an answer.

---

## Open Questions for Derek

Carried until answered. Add to this list rather than resolving items silently.

1. **Can two guests share a seeded reference corpus?** Today a project lives in exactly one Space, so the Syndy pattern — create a Space, move projects into it — does not extend to several people looking at the same seed material without duplicating it. WALK-1 criterion 5 surfaces the options; the choice is Derek's.
2. **Does the Librarian ever get to write without asking?** Sprint 58 assumes suggestions-a-user-accepts. If Derek wants genuinely autonomous jobs ("eventually all projects have descriptions"), that is a different risk posture and needs saying out loud.
3. **How far does "synthesize or summarize research" go before it becomes Q&A?** The two blur. The artifact rule is the current dividing line: summarising *into a saved report* is in scope; answering in the chat box is not.

---

## Key Design Principles

1. **The artifact rule.** Every turn ends in something that lands in the system.
2. **Provenance over cleanliness.** A marked machine-written field beats a tidy corpus you cannot audit.
3. **Citations are not decoration.** If it cannot be cited, it is not asserted about the corpus.
4. **The agent acts as its user.** Never a service role. A user must not reach anything through the Librarian that they cannot reach directly.
5. **Cold start is a feature surface, not an error state.** The empty Space is where the funnel starts.
6. **Record now what you cannot reconstruct later.** Usage and provenance both.
7. **Missions cite human-authored warrants.** Decision #508: an agent-authored next-step, decision or commit body is context, never a mandate.

---

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| The Librarian drifts into being a chat account | The artifact rule, enforced by a test that a general-knowledge question gets no conversational answer |
| Auto-writes corrupt a corpus Derek cares about | Provenance and revert ship *before* any write (Sprint 58 ordering) |
| A grounded answer that quietly is not grounded | Mutation test: a fabricated citation must fail |
| Guests hit a path nobody has walked | WALK-1, before invites |
| Guest cost becomes an open tab | METER-0 records now; policy later, with data |
| Building on unverified retrieval | RAG-1 gates the Q&A sprint, not the arc |
| The LLM framework space moves under us | LIB-0 runs first and is re-run if the arc extends past Sprint 60 |
| Inventing scope again | Every mission carries Derek's verbatim words (decision #508) |

---

## Terminology

- **Librarian** — the agent surface that operates TraceLab's tools on a user's behalf. Not a chatbot.
- **Artifact** — a mission, report, collection, synthesis or document that persists in TraceLab.
- **Corpus claim** — a statement about what TraceLab holds. Always requires a citation.
- **Planning output** — a suggestion, question or framing. Uses world knowledge freely; asserts nothing about the corpus.
- **Guest** — a design pro invited to try TraceLab, in their own Space.

---

## Change Log

- **2026-09-17 UTC, created at Sprint 57 open.** Written from the Sprint 56 review conversation with Derek, which closed the RBAC arc and opened this one. Sprint 57 created in CMOS with five missions (LIB-0, LIB-1 *Requires LIB-0*, WALK-1, METER-0, RAG-1) and zero RBAC missions. The two rules were settled in that conversation: the artifact rule from Derek's "not a backdoor way for someone to have a chat account", and the claim-type boundary after Derek rejected the agent's proposed corpus-only bound on cold-start grounds. The agent's original sequencing — corpus Q&A first, retrieval as the gate for the whole arc — was wrong and was changed: authoring ships first because it works on day one and causes the corpus to exist, and RAG-1 gates the Q&A sprint only. Production baseline recorded above, including three facts that shaped the plan: no one but Derek has ever run a mission, a project lives in exactly one Space, and missions record no cost.

_Truth in data, evidence as the connective tissue, one system._
