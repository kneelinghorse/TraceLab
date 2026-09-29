import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { duplicateApi, type DuplicateComparison, type DuplicatePair, type DuplicateScan } from "@/lib/api/librarian-duplicates";

const button = "rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold disabled:opacity-60";
type Reviews = Record<string, "keep_both" | "dismissed">;

/** Keyed by caller and project by the parent; scanning is always an explicit action. */
export function DuplicateReview({ userId, projectId, projectName }: { userId: string; projectId: string; projectName: string }) {
  const [result, setResult] = useState<DuplicateScan | null>(null);
  const [reviews, setReviews] = useState<Reviews>({});
  const [comparison, setComparison] = useState<DuplicateComparison | null>(null);
  const [restored, setRestored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const active = useRef(true);
  const locked = useRef(false);
  const resultRef = useRef<HTMLElement>(null);
  const comparisonRef = useRef<HTMLElement>(null);
  const compareButton = useRef<HTMLButtonElement | null>(null);
  const focusResults = useRef(false);
  const key = `tracelab.librarian.duplicates.v1:${userId}:${projectId}`;

  useEffect(() => {
    active.current = true;
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved?.result?.project_id === projectId && Array.isArray(saved.result.candidates) && saved.result.coverage) {
        setResult(saved.result); setReviews(saved.reviews || {});
      }
    } catch { /* A broken browser store must not prevent a fresh scan. */ }
    setRestored(true);
    return () => { active.current = false; };
  }, [key, projectId]);

  useEffect(() => {
    if (!restored || !result) return;
    try { localStorage.setItem(key, JSON.stringify({ result, reviews })); }
    catch { /* Review remains available for this visit. */ }
  }, [restored, key, result, reviews]);

  useEffect(() => {
    if (focusResults.current && result) { focusResults.current = false; resultRef.current?.focus(); }
  }, [result]);
  useEffect(() => { if (comparison) comparisonRef.current?.focus(); }, [comparison]);

  async function run(pair?: DuplicatePair) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(""); setNotice(""); setComparison(null);
    try {
      if (pair) {
        const next = await duplicateApi.compare(projectId, pair);
        if (active.current) setComparison(next);
      } else {
        const next = await duplicateApi.scan(projectId);
        if (active.current) { focusResults.current = true; setResult(next); setReviews({}); setNotice("Comparison ready. Your documents are unchanged."); }
      }
    } catch (err) {
      if (active.current) setError(err instanceof Error ? err.message : "The comparison could not load. Try again.");
    } finally {
      locked.current = false;
      if (active.current) setBusy(false);
    }
  }

  function review(pair: DuplicatePair, outcome: Reviews[string]) {
    setReviews(current => ({ ...current, [pair.candidate_id]: outcome }));
    setComparison(null);
    setNotice(outcome === "keep_both" ? "Keep both recorded for your review. Neither document was changed." : "Pair dismissed from your review. Neither document was changed.");
  }

  const coverage = result?.coverage;
  const visible = result?.candidates.filter(pair => !reviews[pair.candidate_id]) ?? [];
  return <section className="panel space-y-4 p-5" aria-label="Duplicate review">
    <header>
      <h2 className="text-lg font-semibold">Review possible duplicates in {projectName}</h2>
      <p className="text-sm text-secondary">Compare extracted text in this project, then decide what to keep. Scanning and review leave your documents unchanged.</p>
    </header>
    <button className={button} disabled={busy} onClick={() => void run()}>{busy ? "Comparing…" : result ? "Scan again" : "Find possible duplicates"}</button>
    <details className="text-sm text-secondary">
      <summary className="cursor-pointer">What does this comparison cover?</summary>
      <p>Examines up to 100 readable documents, each with at most 20,000 characters of extracted text. Empty or longer texts are excluded, and at most 20 pairs are shown. Short or single-passage texts are checked for exact equality only.</p>
      <p>Exact text ignores Unicode presentation, letter case and whitespace. Probable overlap requires at least 80% shared five-word phrases and substantial matching text in two distinct passages of each document. This is measured text overlap, not a probability or a judgment that either source should be deleted.</p>
    </details>
    {result && coverage && <section ref={resultRef} tabIndex={-1} className="space-y-3 focus-visible:ring-2 focus-visible:ring-focus" aria-label="Duplicate results">
      <p className="text-sm text-secondary">Examined {coverage.examined_documents} of {coverage.readable_documents} readable documents. {coverage.empty_documents} without usable text and {coverage.overlong_documents} over the text limit were excluded from {coverage.scanned_documents} scanned documents. {coverage.exact_only_documents} were checked for exact text only. {coverage.limited && "The document limit was reached; this is a partial scan."}</p>
      <p className="text-xs text-secondary">Last requested {new Date(result.scanned_at).toLocaleString()}. Compare sources to refresh access and text before acting.</p>
      {coverage.candidates_limited && <p className="text-sm text-secondary">Showing the first {coverage.pair_limit} of {coverage.candidate_count} matching pairs, with exact matches first.</p>}
      {result.candidates.length === 0 && <p>No possible duplicates found within the examined scope.</p>}
      {visible.map(pair => <article key={pair.candidate_id} className="space-y-3 rounded-lg border border-line p-4">
        <h3 className="font-semibold">{pair.kind === "exact_text" ? "Exact normalized text" : "Probable text overlap"}</h3>
        <ul className="list-inside list-disc break-words text-sm">{pair.documents.map(doc => <li key={doc.id}>{doc.name}</li>)}</ul>
        <p className="text-sm text-secondary">{pair.basis}</p>
        {pair.evidence.map((evidence, index) => <div key={index} className="grid gap-3 text-sm md:grid-cols-2">
          <blockquote className="whitespace-pre-wrap break-words border-l-2 border-line pl-3">{evidence.left_excerpt}</blockquote>
          <blockquote className="whitespace-pre-wrap break-words border-l-2 border-line pl-3">{evidence.right_excerpt}</blockquote>
        </div>)}
        <p className="text-sm text-secondary">{pair.recommendation}</p>
        <div className="flex flex-wrap gap-2">
          <button className={button} disabled={busy} onClick={event => { compareButton.current = event.currentTarget; void run(pair); }}>Compare sources</button>
          <button className={button} disabled={busy} onClick={() => review(pair, "keep_both")}>Keep both</button>
          <button className={button} disabled={busy} onClick={() => review(pair, "dismissed")}>Dismiss pair</button>
        </div>
      </article>)}
      {Object.keys(reviews).length > 0 && <div className="space-y-2 text-sm">
        <p>{Object.keys(reviews).length} pairs reviewed in your browser. No documents were changed.</p>
        <button className={button} onClick={() => setReviews({})}>Review all results again</button>
      </div>}
    </section>}
    {comparison && <section ref={comparisonRef} tabIndex={-1} className="space-y-3 rounded-lg border border-line p-4 focus-visible:ring-2 focus-visible:ring-focus" aria-label="Compare documents">
      <h3 className="font-semibold">Compare current sources</h3>
      <div className="grid gap-4 md:grid-cols-2">{comparison.documents.map(doc => <div key={doc.id} className="min-w-0 space-y-2">
        <Link className="break-words text-accent-text underline" href={doc.href}>{doc.name}</Link>
        <div tabIndex={0} role="region" aria-label={`Source text: ${doc.name}`} className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded border border-line p-3 text-sm">{doc.content}</div>
      </div>)}</div>
      <button className={button} onClick={() => { setComparison(null); compareButton.current?.focus(); }}>Close comparison</button>
    </section>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {notice && <p role="status" className="text-sm text-secondary">{notice}</p>}
  </section>;
}
