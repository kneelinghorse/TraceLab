import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import useSWR from "swr";

import { AuthGate } from "@/components/AuthGate";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { SpacePicker } from "@/components/SpacePicker";
import { useFeedback } from "@/components/ui/useFeedback";
import { useAuth } from "@/contexts/AuthContext";
import {
  ANSWER_BUDGETS,
  librarianApi,
  replyToTranscriptText,
  type AnswerBudget,
  type ChunkRef,
  type DraftResponse,
  type ReplySegment,
  type TranscriptMessage,
} from "@/lib/api/librarian";
import { projectsApi } from "@/lib/api/projects";
import { LibrarianSteps } from "@/components/librarian/LibrarianSteps";
import {
  clearLibrarianState,
  readLibrarianState,
  readOrientationDismissed,
  writeLibrarianState,
  writeOrientationDismissed,
  type Turn,
} from "@/lib/librarian/storage";

/**
 * The Librarian, part 1: a conversation that ends in a mission (LIB-1).
 *
 * Plain text is the Librarian speaking from general knowledge. A highlighted
 * passage is a claim about this project's evidence and links to every entry it
 * cites; the server has already refused anything it could not cite (decision
 * #513). The transcript is resent on every call and the server stores nothing
 * until the user creates the mission (decision #519); this browser keeps it in
 * localStorage so leaving the page does not discard it (LIB-2, decision #527).
 *
 * "Ask the documents" (QA-1, decision #543) answers a question from the
 * project's documents instead: each cited passage links to the chunk it came
 * from, and a question the project cannot support is refused, never guessed.
 */

type Mode = "converse" | "answer";

function toTranscript(turns: Turn[]): TranscriptMessage[] {
  return turns.map((turn) =>
    turn.role === "user"
      ? { role: "user", content: turn.text }
      : { role: "assistant", content: replyToTranscriptText(turn.segments, turn.chunks) || "…" },
  );
}

const STARTERS = [
  "I want to understand why users abandon onboarding, but I don't know where to start.",
  "Help me turn a vague hunch about pricing pages into a research question.",
  "What would a good mission look like for comparing design-system adoption strategies?",
];

function chunkLabel(chunk: ChunkRef) {
  return chunk.chunk_index == null ? chunk.document_name : `${chunk.document_name} #${chunk.chunk_index}`;
}

function SegmentView({ segment, chunks }: { segment: ReplySegment; chunks: Map<string, ChunkRef> }) {
  if (segment.kind === "withheld") {
    return (
      <p role="note" className="rounded-lg border border-warning-line bg-warning-surface px-3 py-2 text-sm text-warning">
        {segment.text}
      </p>
    );
  }
  const cited = segment.citations.length > 0;
  if (segment.kind === "corpus_claim" || cited) {
    const fromDocuments = cited && segment.citations.every((id) => chunks.has(id));
    return (
      <div className="rounded-lg border-l-4 border-accent bg-surface-alt px-3 py-2" data-kind="corpus_claim">
        <p className="text-xs font-semibold uppercase tracking-wide text-accent-text">
          {fromDocuments ? "From this project's documents" : "From this project's evidence"}
        </p>
        <MarkdownRenderer content={segment.text} className="mt-1" />
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Citations">
          {segment.citations.map((id, index) => {
            const chunk = chunks.get(id);
            return (
              <li key={id} className="min-w-0 max-w-full">
                {chunk ? (
                  <Link href={chunk.href} title={chunk.snippet ?? undefined} className="block max-w-full truncate rounded bg-surface px-2 py-0.5 text-xs text-accent-text underline">
                    {chunkLabel(chunk)}
                  </Link>
                ) : (
                  <Link href={`/evidence/${id}`} className="rounded bg-surface px-2 py-0.5 text-xs text-accent-text underline">
                    Evidence {index + 1}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    );
  }
  return <MarkdownRenderer content={segment.text} />;
}

function DraftPanel({
  draft,
  creating,
  onCreate,
  onDismiss,
  panelRef,
}: {
  draft: DraftResponse;
  creating: boolean;
  onCreate: () => void;
  onDismiss: () => void;
  panelRef: RefObject<HTMLElement | null>;
}) {
  const mission = draft.draft;
  const preview = draft.preview;
  const lists: Array<[string, string[] | null | undefined]> = [
    ["Required entities", mission.required_entities],
    ["Excluded entities", mission.excluded_entities],
    ["Constraints", mission.constraints],
    ["Deliverables", mission.deliverables],
  ];
  return (
    <section ref={panelRef} tabIndex={-1} className="panel space-y-4 p-5 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus" aria-label="Mission draft">
      <header className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-secondary">Step 2 of 3 · Mission draft · {mission.mission_id}</p>
        <h2 className="text-xl font-semibold text-foreground">{mission.title}</h2>
        <p className="text-sm text-secondary">Review it here. Creating it saves a draft; nothing runs until you submit it from the mission page.</p>
      </header>
      <dl className="space-y-3">
        <div>
          <dt className="text-sm font-semibold">Objective</dt>
          <dd className="mt-1 whitespace-pre-wrap break-words text-secondary">{mission.objective}</dd>
        </div>
        <div>
          <dt className="text-sm font-semibold">Success criteria</dt>
          <dd>
            <ol className="mt-1 list-decimal space-y-1 pl-5 text-secondary">
              {mission.success_criteria.map((criterion, index) => (
                <li key={`${index}-${criterion.slice(0, 24)}`} className="break-words">{criterion}</li>
              ))}
            </ol>
          </dd>
        </div>
        {mission.background && (
          <div>
            <dt className="text-sm font-semibold">Background</dt>
            <dd className="mt-1 whitespace-pre-wrap break-words text-secondary">{mission.background}</dd>
          </div>
        )}
        {mission.focus && (
          <div>
            <dt className="text-sm font-semibold">Focus</dt>
            <dd className="mt-1 whitespace-pre-wrap break-words text-secondary">{mission.focus}</dd>
          </div>
        )}
        {lists.map(([label, values]) =>
          values && values.length ? (
            <div key={label}>
              <dt className="text-sm font-semibold">{label}</dt>
              <dd className="mt-1 flex flex-wrap gap-2">
                {values.map((value) => (
                  <span key={value} className="rounded bg-surface-alt px-2 py-1 text-sm text-secondary">{value}</span>
                ))}
              </dd>
            </div>
          ) : null,
        )}
        {mission.deliverable_format && (
          <div>
            <dt className="text-sm font-semibold">Deliverable format</dt>
            <dd className="mt-1 break-words text-secondary">{mission.deliverable_format}</dd>
          </div>
        )}
      </dl>

      <section className="rounded-lg border border-line bg-surface p-4" aria-label="Compiled contract">
        <h3 className="text-sm font-semibold">What DeepSearch would run</h3>
        {preview ? (
          <p className="mt-1 text-sm text-secondary">
            {preview.objectives.length.toLocaleString()} research objectives · {preview.evidence_slots.length.toLocaleString()} evidence slots · {preview.acceptance_checks.length.toLocaleString()} acceptance checks · {preview.deliverable_schemas.length.toLocaleString()} deliverable schemas · compiler {preview.compiler_revision.slice(0, 7)} ({preview.fidelity})
          </p>
        ) : (
          <p role="alert" className="mt-1 text-sm text-danger">The contract could not be compiled: {draft.preview_error ?? "unknown error"}</p>
        )}
        {preview && preview.named_entities.length > 0 && (
          <p className="mt-1 text-sm text-secondary">Named entities: {preview.named_entities.join(", ")}</p>
        )}
      </section>

      {(draft.notes.length > 0 || draft.lint_errors.length > 0 || draft.lint_warnings.length > 0) && (
        <ul className="space-y-2" aria-label="Draft review notes">
          {draft.lint_errors.map((violation) => (
            <li key={`e-${violation.rule}-${violation.field}`} className="rounded-lg border border-danger-line bg-danger-surface px-3 py-2 text-sm text-danger">
              <span className="font-semibold">Blocks submission:</span> {violation.message}{violation.suggestion ? ` ${violation.suggestion}` : ""}
            </li>
          ))}
          {draft.lint_warnings.map((violation) => (
            <li key={`w-${violation.rule}-${violation.field}`} className="rounded-lg border border-warning-line bg-warning-surface px-3 py-2 text-sm text-warning">
              {violation.message}{violation.suggestion ? ` ${violation.suggestion}` : ""}
            </li>
          ))}
          {draft.notes.map((note) => (
            <li key={note} className="rounded-lg border border-info-line bg-info-surface px-3 py-2 text-sm text-info">{note}</li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onCreate}
          disabled={creating}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
        >
          {creating ? "Creating…" : "Create draft mission"}
        </button>
        <button type="button" onClick={onDismiss} className="rounded-lg border border-line-strong px-4 py-2 text-sm">
          Keep refining
        </button>
      </div>
      <p className="text-sm text-secondary">Next: the mission page, where you can edit the draft and press Submit to DeepSearch. It waits there until you do.</p>
    </section>
  );
}

function LibrarianContent() {
  const router = useRouter();
  const { user } = useAuth();
  const { notify, feedback } = useFeedback();
  const projects = useSWR(["librarian-projects", user?.user_id], () => projectsApi.listAllProjects());
  const queryProject = typeof router.query.project === "string" ? router.query.project : "";
  const [projectId, setProjectId] = useState(queryProject);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectSpace, setNewProjectSpace] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("converse");
  const [budget, setBudget] = useState<AnswerBudget>("short");
  const [sending, setSending] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [orientationHidden, setOrientationHidden] = useState(false);
  // Which user's stored conversation has been restored; persistence waits for it so a
  // fresh mount never overwrites a saved conversation with an empty one.
  const [restoredFor, setRestoredFor] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const draftPanelRef = useRef<HTMLElement>(null);
  const focusDraftRef = useRef(false);
  const storageUser = user?.user_id ?? "guest";

  useEffect(() => {
    if (queryProject) setProjectId(queryProject);
  }, [queryProject]);
  useEffect(() => {
    const stored = readLibrarianState(storageUser);
    setTurns(stored?.turns ?? []);
    setDraft(stored?.draft ?? null);
    if (!queryProject) setProjectId(stored?.projectId ?? "");
    setOrientationHidden(readOrientationDismissed(storageUser));
    setRestoredFor(storageUser);
  }, [storageUser]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (restoredFor === storageUser) writeLibrarianState(storageUser, { projectId, turns, draft });
  }, [restoredFor, storageUser, projectId, turns, draft]);
  useEffect(() => {
    // Only a draft the user just asked for takes focus; a restored one stays where it was.
    if (!draft || !focusDraftRef.current) return;
    focusDraftRef.current = false;
    const panel = draftPanelRef.current;
    if (!panel) return;
    if (typeof panel.scrollIntoView === "function") panel.scrollIntoView({ behavior: "smooth", block: "start" });
    panel.focus({ preventScroll: true });
  }, [draft]);
  useEffect(() => {
    const log = logRef.current;
    if (log && typeof log.scrollTo === "function") log.scrollTo({ top: log.scrollHeight });
  }, [turns.length, sending]);

  const project = useMemo(() => projects.data?.find((item) => item.id === projectId) ?? null, [projects.data, projectId]);
  // Asking needs a project: an answer comes from one project's documents.
  const answering = mode === "answer" && Boolean(projectId);
  const lastAssistant = [...turns].reverse().find((turn) => turn.role === "assistant");
  const suggested = lastAssistant?.role === "assistant" && lastAssistant.suggested;
  const canDraft = turns.some((turn) => turn.role === "user") && Boolean(projectId) && !sending;
  const started = turns.length > 0;
  const primaryButton = "rounded-xl bg-accent px-5 py-3 font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60";
  const secondaryButton = "rounded-xl border border-line-strong px-5 py-3 font-semibold text-foreground disabled:cursor-not-allowed disabled:opacity-60";

  function startOver() {
    setTurns([]);
    setDraft(null);
    setInput("");
    clearLibrarianState(storageUser);
  }

  function dismissOrientation() {
    writeOrientationDismissed(storageUser);
    setOrientationHidden(true);
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    const next: Turn[] = [...turns, { role: "user", text: trimmed }];
    setTurns(next);
    setInput("");
    setSending(true);
    try {
      const reply = answering
        ? await librarianApi.turn(toTranscript(next), projectId, { maxTokens: ANSWER_BUDGETS[budget] })
        : await librarianApi.turn(toTranscript(next), projectId || null);
      setTurns([
        ...next,
        {
          role: "assistant",
          segments: reply.segments,
          evidence: reply.evidence,
          suggested: reply.suggested_action === "draft_mission",
          ...(answering ? { chunks: reply.chunks, noEvidence: reply.no_evidence } : {}),
        },
      ]);
    } catch (err) {
      notify(err);
      setTurns(turns);
      setInput(trimmed);
    } finally {
      setSending(false);
    }
  }

  async function draftMission() {
    if (!projectId || drafting) return;
    setDrafting(true);
    try {
      const result = await librarianApi.draft(toTranscript(turns), projectId);
      focusDraftRef.current = true;
      setDraft(result);
      notify("Your draft is ready below. Review it, then create it.", "success");
    } catch (err) {
      notify(err);
    } finally {
      setDrafting(false);
    }
  }

  async function createMission() {
    if (!draft || !projectId || creating) return;
    setCreating(true);
    try {
      const result = await librarianApi.createMission(draft.draft, projectId);
      notify(result.created ? "Draft mission created. Review and submit it from the mission page." : "This draft already exists; opening it.", "success");
      // The draft is now a mission; the conversation stays for the next one.
      writeLibrarianState(storageUser, { projectId, turns, draft: null });
      await router.push(`/missions/${result.mission.id}?from=librarian`);
    } catch (err) {
      notify(err);
      setCreating(false);
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newProjectName.trim();
    if (!name || creatingProject) return;
    setCreatingProject(true);
    try {
      const created = await projectsApi.createProject(
        newProjectSpace ? { name, workspace_id: newProjectSpace } : { name },
      );
      await projects.mutate();
      setProjectId(created.id);
      setNewProjectName("");
      setNewProjectSpace("");
      notify(`Project "${created.name}" created. The Librarian's missions will land there.`, "success");
    } catch (err) {
      notify(err);
    } finally {
      setCreatingProject(false);
    }
  }

  function onComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(input);
    }
  }

  return (
    <div className={`mx-auto space-y-6 px-4 py-8 sm:px-6 ${started ? "max-w-6xl" : "max-w-4xl"}`}>
      <Head>
        <title>Librarian · TraceLab</title>
      </Head>
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-foreground">Librarian</h1>
        <p className="text-secondary">
          Describe what you want to learn. The Librarian helps shape it into a research question, then drafts a DeepSearch mission you review and run. Or ask a question about a project&apos;s documents and get an answer that cites them.
        </p>
        <p className="text-sm text-muted">
          Plain text is the Librarian speaking from general knowledge. A highlighted passage is a claim about this project&apos;s documents or evidence and links to what it cites.
        </p>
      </header>

      {!orientationHidden && <LibrarianSteps current={draft ? 2 : 1} onDismiss={dismissOrientation} />}

      <section className="panel space-y-3 p-5" aria-label="Project">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <div className="flex-1">
            <label htmlFor="librarian-project" className="form-label">Project</label>
            <select
              id="librarian-project"
              className="form-input"
              value={projectId}
              onChange={(event) => { setProjectId(event.target.value); setDraft(null); }}
              disabled={projects.isLoading}
            >
              <option value="">No project yet (planning only)</option>
              {(projects.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </div>
          <form onSubmit={createProject} className="flex flex-1 flex-col gap-2">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <label htmlFor="librarian-new-project" className="form-label">New project</label>
                <input
                  id="librarian-new-project"
                  className="form-input"
                  value={newProjectName}
                  onChange={(event) => setNewProjectName(event.target.value)}
                  placeholder="Name a project to hold the mission"
                />
              </div>
              <button type="submit" disabled={creatingProject || !newProjectName.trim()} className="rounded-lg border border-line-strong px-3 py-2 text-sm disabled:opacity-60">
                {creatingProject ? "Creating…" : "Create"}
              </button>
            </div>
            <SpacePicker value={newProjectSpace} onChange={setNewProjectSpace} />
          </form>
        </div>
        {projects.error && <p role="alert" className="text-sm text-danger">Projects could not load. <button type="button" className="underline" onClick={() => void projects.mutate()}>Retry</button></p>}
        {!projectId && !projects.isLoading && (
          <p className="text-sm text-secondary">
            Without a project the Librarian can only plan: it has no evidence to cite and nowhere to save a mission. Pick one or create one when you are ready.
          </p>
        )}
        {project && <p className="text-sm text-secondary">Missions will be created in <Link href={`/projects/${project.id}`} className="text-accent-text underline">{project.name}</Link>.</p>}
      </section>

      <section className="panel p-5" aria-label="Conversation with the Librarian">
        {started && (
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-secondary">{draft ? "Step 2 of 3 · Review the draft below" : "Step 1 of 3 · Shape it"}</p>
            <div className="flex gap-2">
              <button type="button" onClick={() => setExpanded((value) => !value)} aria-pressed={expanded} className="rounded-lg border border-line px-3 py-1 text-xs text-secondary hover:text-foreground">
                {expanded ? "Compact view" : "Expand transcript"}
              </button>
              <button type="button" onClick={startOver} className="rounded-lg border border-line px-3 py-1 text-xs text-secondary hover:text-foreground">
                Start over
              </button>
            </div>
          </div>
        )}
        <div
          ref={logRef}
          role="log"
          aria-live="polite"
          aria-label="Transcript"
          className={`space-y-4 overflow-y-auto pr-1 ${expanded ? "" : started ? "min-h-[50vh] max-h-[75vh]" : "max-h-[60vh]"}`}
        >
          {turns.length === 0 && answering && (
            <p className="text-secondary">
              Ask a question about {project?.name ?? "this project"}&apos;s documents. The answer comes only from them and every claim links to the chunk it came from; if nothing there answers it, the Librarian says so.
            </p>
          )}
          {turns.length === 0 && !answering && (
            <div className="space-y-3">
              <p className="text-secondary">Start with the question you cannot quite phrase yet. For example:</p>
              <ul className="space-y-2">
                {STARTERS.map((starter) => (
                  <li key={starter}>
                    <button type="button" onClick={() => void send(starter)} className="w-full rounded-lg border border-line px-3 py-2 text-left text-sm text-secondary hover:border-line-strong hover:text-foreground">
                      {starter}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {turns.map((turn, index) => {
            if (turn.role === "user") {
              return (
                <article key={index} className="ml-auto max-w-[85%] rounded-2xl bg-accent px-4 py-2 text-on-accent" aria-label="You">
                  <p className="whitespace-pre-wrap break-words">{turn.text}</p>
                </article>
              );
            }
            if (turn.noEvidence) {
              // The refusal asserts nothing, so it is never styled as a claim.
              return (
                <article key={index} className="max-w-[95%]" aria-label="Librarian">
                  <p role="note" data-kind="refusal" className="rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-secondary">
                    {turn.segments.map((segment) => segment.text).join(" ")}
                  </p>
                </article>
              );
            }
            const chunks = new Map((turn.chunks ?? []).map((chunk) => [chunk.id, chunk]));
            return (
              <article key={index} className="max-w-[95%] space-y-2" aria-label="Librarian">
                {turn.segments.map((segment, segmentIndex) => (
                  <SegmentView key={segmentIndex} segment={segment} chunks={chunks} />
                ))}
              </article>
            );
          })}
          {sending && <p role="status" className="text-sm text-muted">{answering ? "The Librarian is reading the documents…" : "The Librarian is thinking…"}</p>}
        </div>

        <div className="mt-4 space-y-2 text-sm">
          <div role="radiogroup" aria-label="How the Librarian replies" className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <label className="flex items-center gap-2">
              <input type="radio" name="librarian-mode" value="converse" checked={!answering} onChange={() => setMode("converse")} />
              Talk it through
            </label>
            <label className={`flex items-center gap-2 ${projectId ? "" : "text-muted"}`} title={projectId ? undefined : "Choose a project to ask about its documents"}>
              <input type="radio" name="librarian-mode" value="answer" checked={answering} disabled={!projectId} onChange={() => setMode("answer")} />
              Ask the documents
            </label>
          </div>
          {answering && (
            <div role="radiogroup" aria-label="Answer length" className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <label className="flex items-center gap-2">
                <input type="radio" name="librarian-budget" value="short" checked={budget === "short"} onChange={() => setBudget("short")} />
                Short answer
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="librarian-budget" value="full" checked={budget === "full"} onChange={() => setBudget("full")} />
                Full synthesis
              </label>
            </div>
          )}
        </div>
        <form
          onSubmit={(event) => { event.preventDefault(); void send(input); }}
          className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end"
        >
          <div className="flex-1">
            <label htmlFor="librarian-composer" className="sr-only">Message the Librarian</label>
            <textarea
              id="librarian-composer"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={onComposerKey}
              rows={2}
              placeholder={answering ? `Ask a question about ${project?.name ?? "this project"}'s documents…` : "Ask anything, or describe what you want to research…"}
              className="w-full resize-none rounded-xl border border-line bg-surface px-4 py-3 text-foreground placeholder:text-muted focus:border-info-line focus:outline-none focus:ring-2 focus:ring-focus"
            />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={sending || !input.trim()} className={suggested ? secondaryButton : primaryButton}>
              {sending ? (answering ? "Asking…" : "Sending…") : answering ? "Ask" : "Send"}
            </button>
            <button
              type="button"
              onClick={() => void draftMission()}
              disabled={!canDraft || drafting}
              title={projectId ? undefined : "Choose a project to draft a mission into"}
              data-suggested={suggested ? "true" : undefined}
              className={suggested ? primaryButton : secondaryButton}
            >
              {drafting ? "Drafting…" : "Draft a mission"}
            </button>
          </div>
        </form>
        {suggested && !draft && <p className="mt-2 text-sm text-accent-text">The Librarian thinks there is enough here for a mission.</p>}
      </section>

      {draft && <DraftPanel draft={draft} creating={creating} onCreate={() => void createMission()} onDismiss={() => setDraft(null)} panelRef={draftPanelRef} />}
      {feedback}
    </div>
  );
}

export default function LibrarianPage() {
  return (
    <AuthGate>
      <LibrarianContent />
    </AuthGate>
  );
}
