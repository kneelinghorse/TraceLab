# Document duplicate review (DUP-1)

Decision #554 implements the [Sprint 60 handoff](../planning/sprint-60-HANDOFF.md), following the [architecture template](../foundational-docs/tech_arch_template.md). CMOS owns mission status. This is a bounded, on-demand comparison of extracted text, with no provider, vector search, indexing job or corpus write.

## Request and scope

Both routes under `/api/v1/librarian` require a human principal, a live selected project and that caller's project-read authorization. The shared document-read policy and selected-project predicate apply before text analysis, including for admins. Request schemas forbid unknown fields.

| Route | Input | Result |
| --- | --- | --- |
| `POST /duplicates/scan` | `project_id` | Timestamp, method version, bounded candidate list and coverage counts |
| `POST /duplicates/compare` | `project_id`, two distinct `document_ids`, 64-character `candidate_id` | Fresh comparison evidence, resolving document links and both complete bounded texts |

Scan orders live readable documents by UUID and considers the first 100. A SQL CASE suppresses loading text over 20,000 characters; raw file bytes are never selected. Empty or whitespace-only content and overlong text are excluded. No truncated prefix can qualify as exact. Counts disclose readable documents, scanned documents, examined texts, empty/overlong exclusions, exact-only inputs, and whether the document limit was reached. These are counts within the selected scope, not claims about the broader library.

## Candidate method

`normalized-text-five-word-phrases-v1` uses complete extracted text. Titles, tags and topic similarity are not evidence. Exact normalized text requires non-empty equality after Unicode NFKC, case folding and whitespace collapse; punctuation remains significant. A short identical note may therefore match exactly, without implying that either document should be deleted.

Probable overlap requires all of:

- At least 60 word tokens in each document and shorter/longer token count ratio of at least 0.80.
- At least 40 shared distinct five-word phrases, with Jaccard overlap of at least 0.80.
- At least two distinct paragraphs of at least 15 words in each document, each sharing at least 60% of its phrases with the other document. Repeated copies of the same normalized paragraph count once. Paragraphs are separated by blank lines.

This conservative rule excludes a single reused disclaimer even when most text overlaps. Short and single-passage texts can match exactly but are outside probable-overlap coverage. The score measures lexical overlap, never confidence or a probability. It is not a semantic deduplication system, and it may miss paraphrases or differently structured revisions. Calibration fixtures include exact copies, edited revisions, identical titles with different content, related topics, a dominant shared disclaimer, Unicode/short text, empty text and overlong matching prefixes.

At most 4,950 pairs are considered. Exact matches sort first, then overlap score and stable document identities; at most 20 pairs are returned. Total candidate count and result truncation are disclosed. Each pair contains both source identities, excerpts, the measured basis and advice to compare dates, annotations and purpose before deciding what to retain.

## Review and freshness

Candidate identity hashes the method version, ordered document IDs and each raw text's SHA-256. Compare reloads both sources under current liveness, access and selected-project scope, then recomputes the candidate. Missing/out-of-scope sources return 404; changed text or fabricated candidate identity returns 409. Project authorization retains normal 403/404 behavior. The client supplies no evidence, source text or remediation operation.

The UI requests no scan on page load, focus, reconnect or reload. Results and keep-both/dismiss decisions use the existing per-user/project browser-state pattern; raw comparison text is not persisted there. Cached results are labeled with their scan time, and source comparison always makes a fresh authorized request. Full source links appear only with that refreshed comparison. New account/project panels cannot receive a late prior response.

Keep-both and dismiss only affect the caller's browser review; both can be revisited without scanning. They do not merge, delete, archive, reparent, tag, rewrite chunks or change collections/relationships. Existing document controls remain the place for a person to act after reviewing. There is no model call or paid usage record for this deterministic analysis. Both UI operations are classified REST-only-by-design in the MCP parity manifest, with no package surface change.
