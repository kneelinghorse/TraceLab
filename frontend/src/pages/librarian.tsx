import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import useSWR from "swr";

import { AuthGate } from "@/components/AuthGate";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { useFeedback } from "@/components/ui/useFeedback";
import { useAuth } from "@/contexts/AuthContext";
import {
  librarianApi,
  replyToTranscriptText,
  type DraftResponse,
  type EvidenceRef,
  type ReplySegment,
  type TranscriptMessage,
} from "@/lib/api/librarian";
import { projectsApi } from "@/lib/api/projects";

/**
 * The Librarian, part 1: a conversation that ends in a mission (LIB-1).
 *
 * Plain text is the Librarian speaking from general knowledge. A highlighted
 * passage is a claim about this project's evidence and links to every entry it
 * cites; the server has already refused anything it could not cite (decision
 * #513). The transcript lives here and is resent on every call: nothing is
 * stored until the user creates the mission (decision #519).
 */

type Turn =
  | { role: "user"; text: string }
  | { role: "assistant"; segments: ReplySegment[]; evidence: EvidenceRef[]; suggested: boolean };

function toTranscript(turns: Turn[]): TranscriptMessage[] {
  return turns.map((turn) =>
    turn.role === "user"
      ? { role: "user", content: turn.text }
      : { role: "assistant", content: replyToTranscriptText(turn.segments) || "…" },
  );
}

const STARTERS = [
  "I want to understand why users abandon onboarding, but I don't know where to start.",
  "Help me turn a vague hunch about pricing pages into a research question.",
  "What would a good mission look like for comparing design-system adoption strategies?",
];

function SegmentView({ segment }: { segment: ReplySegment }) {
  if (segment.kind === "withheld") {
    return (
      <p role="note" className="rounded-lg border border-warning-line bg-warning-surface px-3 py-2 text-sm text-warning">
        {segment.text}
      </p>
    );
  }
  const cited = segment.citations.length > 0;
  if (segment.kind === "corpus_claim" || cited) {
    return (
      <div className="rounded-lg border-l-4 border-accent bg-surface-alt px-3 py-2" data-kind="corpus_claim">
        <p className="text-xs font-semibold uppercase tracking-wide text-accent-text">From this project&apos;s evidence</p>
        <MarkdownRenderer content={segment.text} className="mt-1" />
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Citations">
          {segment.citations.map((id, index) => (
            <li key={id}>
              <Link href={`/evidence/${id}`} className="rounded bg-surface px-2 py-0.5 text-xs text-accent-text underline">
                Evidence {index + 1}
              </Link>
            </li>
          ))}
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
}: {
  draft: DraftResponse;
  creating: boolean;
  onCreate: () => void;
  onDismiss: () => void;
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
    <section className="panel space-y-4 p-5" aria-label="Mission draft">
      <header className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-secondary">Mission draft · {mission.mission_id}</p>
        <h2 className="text-xl font-semibold text-foreground">{mission.title}</h2>
        <p className="text-sm text-secondary">Review it here. Creating it saves a draft you can edit and submit from the mission page; nothing runs until you submit.</p>
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
  const [creatingProject, setCreatingProject] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (queryProject) setProjectId(queryProject);
  }, [queryProject]);
  useEffect(() => {
    const log = logRef.current;
    if (log && typeof log.scrollTo === "function") log.scrollTo({ top: log.scrollHeight });
  }, [turns.length, sending]);

  const project = useMemo(() => projects.data?.find((item) => item.id === projectId) ?? null, [projects.data, projectId]);
  const lastAssistant = [...turns].reverse().find((turn) => turn.role === "assistant");
  const suggested = lastAssistant?.role === "assistant" && lastAssistant.suggested;
  const canDraft = turns.some((turn) => turn.role === "user") && Boolean(projectId) && !sending;

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    const next: Turn[] = [...turns, { role: "user", text: trimmed }];
    setTurns(next);
    setInput("");
    setSending(true);
    try {
      const reply = await librarianApi.turn(toTranscript(next), projectId || null);
      setTurns([
        ...next,
        { role: "assistant", segments: reply.segments, evidence: reply.evidence, suggested: reply.suggested_action === "draft_mission" },
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
      setDraft(await librarianApi.draft(toTranscript(turns), projectId));
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
      await router.push(`/missions/${result.mission.id}`);
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
      const created = await projectsApi.createProject({ name });
      await projects.mutate();
      setProjectId(created.id);
      setNewProjectName("");
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
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
      <Head>
        <title>Librarian · TraceLab</title>
      </Head>
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-foreground">Librarian</h1>
        <p className="text-secondary">
          Describe what you want to learn. The Librarian helps shape it into a research question, then drafts a DeepSearch mission you review and run.
        </p>
        <p className="text-sm text-muted">
          Plain text is the Librarian speaking from general knowledge. A highlighted passage is a claim about this project&apos;s evidence and links to the entries it cites.
        </p>
      </header>

      <section className="panel space-y-3 p-5" aria-label="Project">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
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
          <form onSubmit={createProject} className="flex flex-1 items-end gap-2">
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
        <div ref={logRef} role="log" aria-live="polite" aria-label="Transcript" className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {turns.length === 0 && (
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
          {turns.map((turn, index) =>
            turn.role === "user" ? (
              <article key={index} className="ml-auto max-w-[85%] rounded-2xl bg-accent px-4 py-2 text-on-accent" aria-label="You">
                <p className="whitespace-pre-wrap break-words">{turn.text}</p>
              </article>
            ) : (
              <article key={index} className="max-w-[95%] space-y-2" aria-label="Librarian">
                {turn.segments.map((segment, segmentIndex) => (
                  <SegmentView key={segmentIndex} segment={segment} />
                ))}
              </article>
            ),
          )}
          {sending && <p role="status" className="text-sm text-muted">The Librarian is thinking…</p>}
        </div>

        <form
          onSubmit={(event) => { event.preventDefault(); void send(input); }}
          className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end"
        >
          <div className="flex-1">
            <label htmlFor="librarian-composer" className="sr-only">Message the Librarian</label>
            <textarea
              id="librarian-composer"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={onComposerKey}
              rows={2}
              placeholder="Ask anything, or describe what you want to research…"
              className="w-full resize-none rounded-xl border border-line bg-surface px-4 py-3 text-foreground placeholder:text-muted focus:border-info-line focus:outline-none focus:ring-2 focus:ring-focus"
            />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={sending || !input.trim()} className="rounded-xl bg-accent px-5 py-3 font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60">
              {sending ? "Sending…" : "Send"}
            </button>
            <button
              type="button"
              onClick={() => void draftMission()}
              disabled={!canDraft || drafting}
              title={projectId ? undefined : "Choose a project to draft a mission into"}
              className={`rounded-xl border px-5 py-3 font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${suggested ? "border-accent text-accent-text" : "border-line-strong text-foreground"}`}
            >
              {drafting ? "Drafting…" : "Draft a mission"}
            </button>
          </div>
        </form>
        {suggested && !draft && <p className="mt-2 text-sm text-accent-text">The Librarian thinks there is enough here for a mission.</p>}
      </section>

      {draft && <DraftPanel draft={draft} creating={creating} onCreate={() => void createMission()} onDismiss={() => setDraft(null)} />}
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
