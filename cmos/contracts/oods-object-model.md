# TraceLab ↔ OODS research object contract

Guiding plan: [Sprint 50–53 UX overhaul](../foundational-docs/roadmap-sprints-50-53-ux-overhaul.md), UX-1. This is a presentation mapping, not a database migration or a replacement for the [mission-authoring boundary contract](mission-authoring-contract.md). The API, PostgreSQL constraints and existing authorization remain authoritative. The SQLite mission workspace only records the build; none of these entities moves into CMOS.

## Source and scope

Seven alpha objects live in Forge `objects/research/`: Project (container), Document and Chunk (data), Collection (context), Mission (job), Report (synthesis), Evidence (data). Space reuses Organization; identity reuses User. The alpha label means research composition is new; preview fixtures are not live TraceLab data or production certification. No npm publication is involved; Forge’s existing CI still verifies its portable bundle.

Forge base: `114a268ea10b9141bc96925c69132179c7c4b334`. Implementation is reviewed in [Forge PR105](https://github.com/kneelinghorse/OODS-Forge/pull/105). Current source revision, retained receipts and outstanding gates are recorded in the [UX-1 validation report](../reports/sprint-50/ux-1-validation.json). Backlog request: `f091c849-fe1a-49d5-93ee-b8029219685a`, TraceLab → `cmos://derek/forge`. This is the roadmap-required request; no Forge reconnect or general status notices are required.

The companion [machine-readable contract](oods-object-model.json) lists each model field, its Python annotation, presentation destination and object field constraints. The tests fail when a model or field changes without a mapping update. Tables below are the readable export of that contract. All fields in the seven schema modules are included, including create/update inputs, pagination and error envelopes; nested document event/tag shapes are included separately.

## Projection rules

- Keep every original field. `name`/`title`/`claim` feeds Labelled.label; Project and Collection description, Mission objective, and Evidence summary feed Labelled.description. Long claims and objectives remain complete in their source fields; truncation belongs only to display. A label alias is not another persisted column.
- Project uses active/archived/completed; Report uses draft/final. Project's API currently accepts arbitrary strings and nullable status: an unrecognized or missing value must remain visible as unknown, never silently become active. Mission uses exactly draft/queued/in_progress/completed/blocked/cancelled/validation_failed. Its `id` is the UUID; `mission_id` is a human identifier, not a replacement for the UUID.
- Document status is a **display projection**, not a new API status field. Use a latest explicit processing failure when available, then embedded, chunked, processed, pending in that priority. Null or missing booleans are unknown, not false. Retain all three booleans and processing events. Historical failed events must not override a later successful stage; validation_status is a separate dimension. `uploaded_at` feeds created_at only when present; the current response has no document updated_at.
- Evidence disposition is classification, not lifecycle. Its four exact values map to one fixed primary category with the same ID and a readable label. Keep original tags as supplied; the adapter may project strings into Classifiable Tag records for presentation, but must not imply synonym collapsing or moderation happened. `source_sighting_count` is the server count (minimum one); never count the current results page to infer it.
- Use nullable authoritative `owner_id` from ProjectRead and LedgerEntryRead. Current Document, Collection, Mission and Report response models omit their database ownership fields, so their Ownerable display is unavailable. Never infer ownership from `created_by`, legacy `user_id`, a project owner, or the current logged-in user. `workspace_id` links a Space/Organization; it is not an owner ID. Unknown or inaccessible owners are not looked up outside existing RBAC.
- Timestampable event fields and Stateful history are optional projections. Mission queued_at/started_at/completed_at can supply named events; preserve missing dates. A history requires real event records. `created_at` and `updated_at` alone do not prove every intervening transition. Do not fabricate actors, elapsed phases, last events or allowed transitions.
- Mission cancellation is immediate and ends at **cancelled**. The Forge generated store must use a state declared by the object and cannot introduce pending_cancellation or a period-end checkbox. Subscription's existing deferred flow remains intact. The generated local prototype is not wired to TraceLab's REST lifecycle; UX-6 must bind the authorized server operation and display server errors before claiming cancellation succeeded.
- Chunk supports **inline only**, enforced by the Forge composer. It is an excerpt inside Document; no new Chunk route exists. Content and offsets retain their source-document relationship, including previous/next chunk IDs.
- Searchable, Filterable and Pageable describe control state, not persisted entity columns. page/page_size and total come from the endpoint envelope; totalPages may be derived from that total and page_size. Search, filters, totals and ownership must not be inferred from one response page. Collections currently omit tags from their public responses; a Taggable declaration does not justify showing fabricated tags.
- `raw_content`, embedding IDs, file paths, compiler envelopes and execution metadata remain mapped for fidelity; they are not automatically displayed or exposed as inputs. Retain request validators and privacy boundaries. Server-derived/read-only fields stay read-only even if a generic generated form contains them.

## Supported compositions

All six page-level objects support list/detail/timeline; Chunk supports inline. Mission also has a saved workflow with list/detail/form/timeline and loading/empty/error/success states. Saved schema names are `tracelab-<object>-<context>-v1`; the schema store's monotonic version is separate from this consumer name. Schemas and React design_preview receipts are retained under `cmos/reports/sprint-50/oods-previews/`; Mission list/detail/timeline and Evidence list/detail are measured at 390/820/1440 in both themes. These are Forge prototypes for later implementation missions, not deployed TraceLab screenshots.

## Universal objects

| TraceLab value | Existing OODS target | Boundary |
|---|---|---|
| Space ID / workspace_id | Organization.organization_id | Nullable association; do not invent domain, billing plan or communications data |
| Space name | Organization.label | Name only; existing Space API is authoritative |
| Authenticated or referenced user ID | User.user_id | Server-authorized identity only |
| User name/email/role | Existing User schema fields | Preserve API fields and role policy; no new identity object |

## API field map

### Project

Source: `app.schemas.project`. Traits: `content/Labelled`, `lifecycle/Stateful`, `lifecycle/Timestampable`, `structural/Ownerable`, `behavioral/Taggable`, `behavioral/Searchable`, `behavioral/Filterable`, `behavioral/Pageable`.

| Field | Pydantic models | Presentation destination |
|---|---|---|
| `name` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead`, `ProjectStats` | Project.name → Labelled.label (display alias) |
| `description` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead` | Project.description |
| `mission_protocol_id` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead` | Project.mission_protocol_id |
| `research_type` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead` | Project.research_type |
| `methodology` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead` | Project.methodology |
| `status` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead` | Project.status → Stateful.status |
| `quality_score` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead` | Project.quality_score |
| `last_quality_check` | `ProjectBase`, `ProjectCreate`, `ProjectUpdate`, `ProjectRead` | Project.last_quality_check |
| `id` | `ProjectRead` | Project.id |
| `created_at` | `ProjectRead` | Project.created_at → Timestampable.created_at |
| `updated_at` | `ProjectRead` | Project.updated_at → Timestampable.updated_at |
| `owner_id` | `ProjectRead` | Project.owner_id → Ownerable.owner_id (nullable) |
| `user_id` | `ProjectRead` | Project.user_id |
| `workspace_id` | `ProjectRead` | Project.workspace_id |
| `project_id` | `ProjectStats` | Project.id (join aggregate by project_id) |
| `document_count` | `ProjectStats` | Project.document_count |
| `chunk_count` | `ProjectStats` | Project.chunk_count |
| `report_count` | `ProjectStats` | Project.report_count |
| `total_tokens` | `ProjectStats` | Project.total_tokens |
| `last_updated` | `ProjectStats` | Project.last_updated |

### Document

Source: `app.schemas.document`. Traits: `content/Labelled`, `lifecycle/Stateful`, `lifecycle/Timestampable`, `structural/Ownerable`, `core/Classifiable`, `behavioral/Searchable`, `behavioral/Filterable`, `behavioral/Pageable`.

| Field | Pydantic models | Presentation destination |
|---|---|---|
| `project_id` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.project_id |
| `name` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.name → Labelled.label (display alias) |
| `file_path` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead` | Document.file_path |
| `file_type` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.file_type |
| `content` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead` | Document.content |
| `raw_content` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead` | Document.raw_content |
| `uploaded_at` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.uploaded_at |
| `file_size` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.file_size |
| `mime_type` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.mime_type |
| `source_type` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.source_type |
| `participant_count` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead` | Document.participant_count |
| `collection_date` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead` | Document.collection_date |
| `processed` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.processed |
| `chunked` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.chunked |
| `embedded` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.embedded |
| `transcription_accuracy` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead` | Document.transcription_accuracy |
| `validation_status` | `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentListItem` | Document.validation_status |
| `id` | `DocumentRead`, `DocumentListItem` | Document.id |
| `chunks` | `DocumentRead` | Document.chunks |
| `tags` | `DocumentRead` | Document.tags |
| `processing_events` | `DocumentRead` | Document.processing_events |
| `chunk_count` | `DocumentRead` | Document.chunk_count |
| `total_tokens` | `DocumentRead` | Document.total_tokens |
| `word_count` | `DocumentRead` | Document.word_count |
| `preview` | `DocumentRead` | Document.preview |

### Chunk

Source: `app.schemas.chunk`. Traits: `content/Labelled`.

| Field | Pydantic models | Presentation destination |
|---|---|---|
| `document_id` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkRead` | Chunk.document_id |
| `chunk_index` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.chunk_index |
| `content` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.content → Labelled.label (display alias) |
| `embedding_id` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.embedding_id |
| `token_count` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.token_count |
| `start_char` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.start_char |
| `end_char` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.end_char |
| `prev_chunk_id` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.prev_chunk_id |
| `next_chunk_id` | `DocumentChunkBase`, `DocumentChunkCreate`, `DocumentChunkUpdate`, `DocumentChunkRead` | Chunk.next_chunk_id |
| `id` | `DocumentChunkRead` | Chunk.id |
| `created_at` | `DocumentChunkRead` | Chunk.created_at → Timestampable.created_at |

### Collection

Source: `app.schemas.collection`. Traits: `content/Labelled`, `lifecycle/Timestampable`, `structural/Ownerable`, `behavioral/Taggable`, `behavioral/Searchable`, `behavioral/Filterable`, `behavioral/Pageable`.

| Field | Pydantic models | Presentation destination |
|---|---|---|
| `chunk_id` | `CollectionItemBase`, `CollectionItemCreate`, `CollectionItemResponse` | Collection.items[].chunk_id |
| `notes` | `CollectionItemBase`, `CollectionItemCreate`, `CollectionItemResponse` | Collection.items[].notes |
| `id` | `CollectionItemResponse` | Collection.items[].id |
| `collection_id` | `CollectionItemResponse` | Collection.items[].collection_id |
| `added_at` | `CollectionItemResponse` | Collection.items[].added_at |
| `chunk_content` | `CollectionItemResponse` | Collection.items[].chunk_content |
| `document_id` | `CollectionItemResponse` | Collection.items[].document_id |
| `name` | `CollectionBase`, `CollectionCreate`, `CollectionUpdate`, `CollectionResponse`, `CollectionDetailResponse` | Collection.name → Labelled.label (display alias) |
| `description` | `CollectionBase`, `CollectionCreate`, `CollectionUpdate`, `CollectionResponse`, `CollectionDetailResponse` | Collection.description |
| `id` | `CollectionResponse`, `CollectionDetailResponse` | Collection.id |
| `created_at` | `CollectionResponse`, `CollectionDetailResponse` | Collection.created_at → Timestampable.created_at |
| `updated_at` | `CollectionResponse`, `CollectionDetailResponse` | Collection.updated_at → Timestampable.updated_at |
| `item_count` | `CollectionResponse`, `CollectionDetailResponse` | Collection.item_count |
| `items` | `CollectionDetailResponse` | Collection.items |
| `data` | `CollectionListResponse` | Transport/request envelope; not a displayed object field. |
| `total` | `CollectionListResponse` | Transport/request envelope; not a displayed object field. |

### Mission

Source: `app.schemas.mission`. Traits: `content/Labelled`, `lifecycle/Stateful`, `lifecycle/Timestampable`, `structural/Ownerable`, `behavioral/Taggable`, `lifecycle/Cancellable`, `behavioral/Searchable`, `behavioral/Filterable`, `behavioral/Pageable`.

| Field | Pydantic models | Presentation destination |
|---|---|---|
| `mission_id` | `MissionBase`, `MissionCreate`, `MissionResponse`, `MissionRead`, `MissionStatusResponse`, `MissionSubmitResponse`, `MissionActionableError`, `MissionContractPreviewResponse` | Mission.mission_id |
| `title` | `MissionBase`, `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.title → Labelled.label (display alias) |
| `objective` | `MissionBase`, `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.objective |
| `success_criteria` | `MissionBase`, `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.success_criteria |
| `project_id` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionContractPreviewResponse` | Mission.project_id |
| `context` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.context |
| `deliverables` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.deliverables |
| `research_phases` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.research_phases |
| `tags` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.tags |
| `metadata` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.metadata |
| `background` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.background |
| `focus` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.focus |
| `references` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.references |
| `required_entities` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.required_entities |
| `excluded_entities` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.excluded_entities |
| `expected_output_schema` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.expected_output_schema |
| `coverage_thresholds` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionContractPreviewResponse` | Mission.coverage_thresholds |
| `validation_thresholds` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionContractPreviewResponse` | Mission.validation_thresholds |
| `deliverable_format` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.deliverable_format |
| `max_loops` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.max_loops |
| `min_loops` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.min_loops |
| `constraints` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.constraints |
| `status` | `MissionCreate`, `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionStatusResponse`, `MissionSubmitResponse`, `ReportPromotionResponse` | Mission.status → Stateful.status |
| `created_by` | `MissionCreate`, `MissionResponse`, `MissionRead` | Mission.created_by |
| `deepsearch_job_id` | `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.deepsearch_job_id |
| `result_document_ids` | `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.result_document_ids |
| `result_report_id` | `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.result_report_id |
| `result_markdown` | `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.result_markdown |
| `result_protocol` | `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.result_protocol |
| `error_message` | `MissionUpdate`, `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.error_message |
| `execution_metadata` | `MissionUpdate`, `MissionResponse`, `MissionRead` | Mission.execution_metadata |
| `id` | `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.id |
| `project_name` | `MissionResponse`, `MissionRead` | Mission.project_name |
| `queued_at` | `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.queued_at |
| `started_at` | `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.started_at |
| `completed_at` | `MissionResponse`, `MissionRead`, `MissionStatusResponse` | Mission.completed_at |
| `created_at` | `MissionResponse`, `MissionRead` | Mission.created_at → Timestampable.created_at |
| `updated_at` | `MissionResponse`, `MissionRead` | Mission.updated_at → Timestampable.updated_at |
| `progress_percent` | `MissionStatusResponse` | Mission.progress_percent |
| `current_phase` | `MissionStatusResponse` | Mission.current_phase |
| `deepsearch_attempt_count` | `MissionStatusResponse` | Mission.deepsearch_attempt_count |
| `lease_expires_at` | `MissionStatusResponse` | Mission.lease_expires_at |
| `materialization_pending` | `MissionStatusResponse` | Mission.materialization_pending |
| `materialization_status` | `MissionStatusResponse` | Mission.materialization_status |
| `materialization_attempt_count` | `MissionStatusResponse` | Mission.materialization_attempt_count |
| `materialization_error` | `MissionStatusResponse` | Mission.materialization_error |
| `search_ready` | `MissionStatusResponse` | Mission.search_ready |
| `rule` | `MissionLintViolation` | Transport/request envelope; not a displayed object field. |
| `field` | `MissionLintViolation` | Transport/request envelope; not a displayed object field. |
| `message` | `MissionLintViolation`, `MissionLintErrorDetail`, `MissionSubmitResponse`, `MissionActionableError`, `ReportPromotionResponse` | Transport/request envelope; not a displayed object field. |
| `suggestion` | `MissionLintViolation`, `MissionActionableError` | Transport/request envelope; not a displayed object field. |
| `errors` | `MissionLintErrorDetail` | Transport/request envelope; not a displayed object field. |
| `warnings` | `MissionLintErrorDetail`, `MissionSubmitResponse` | Transport/request envelope; not a displayed object field. |
| `mode` | `MissionSubmitResponse` | Transport/request envelope; not a displayed object field. |
| `uuid` | `MissionSubmitResponse`, `MissionActionableError` | Transport/request envelope; not a displayed object field. |
| `job_id` | `MissionSubmitResponse` | Transport/request envelope; not a displayed object field. |
| `current_status` | `MissionActionableError` | Transport/request envelope; not a displayed object field. |
| `detail` | `MissionErrorResponse` | Transport/request envelope; not a displayed object field. |
| `document_id` | `ReportPromotionResponse` | Transport/request envelope; not a displayed object field. |
| `document_name` | `ReportPromotionResponse` | Transport/request envelope; not a displayed object field. |
| `chunk_count` | `ReportPromotionResponse` | Transport/request envelope; not a displayed object field. |
| `mission_uuid` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `contract_version` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `compiler_revision` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `fidelity` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `named_entities` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `objectives` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `evidence_slots` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `acceptance_checks` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |
| `deliverable_schemas` | `MissionContractPreviewResponse` | Transport/request envelope; not a displayed object field. |

### Report

Source: `app.schemas.report`. Traits: `content/Labelled`, `lifecycle/Stateful`, `lifecycle/Timestampable`, `structural/Ownerable`, `behavioral/Searchable`, `behavioral/Filterable`, `behavioral/Pageable`.

| Field | Pydantic models | Presentation destination |
|---|---|---|
| `chunk_id` | `CitationSchema` | Report.citations[].chunk_id |
| `document_id` | `CitationSchema` | Report.citations[].document_id |
| `excerpt` | `CitationSchema` | Report.citations[].excerpt |
| `id` | `ReportSourceSchema` | Report.sources[].id |
| `report_id` | `ReportSourceSchema` | Report.sources[].report_id |
| `source_type` | `ReportSourceSchema` | Report.sources[].source_type |
| `source_id` | `ReportSourceSchema` | Report.sources[].source_id |
| `added_at` | `ReportSourceSchema` | Report.sources[].added_at |
| `title` | `ReportBase`, `ReportCreate`, `ReportUpdate`, `ReportResponse`, `ReportDetailResponse`, `ReportListItem` | Report.title → Labelled.label (display alias) |
| `collection_id` | `ReportCreate` | Transport/request envelope; not a displayed object field. |
| `chunk_ids` | `ReportCreate` | Transport/request envelope; not a displayed object field. |
| `project_id` | `ReportCreate`, `ReportDetailResponse`, `ReportListItem` | Report.project_id |
| `prompt` | `ReportCreate`, `ReportDetailResponse` | Report.prompt |
| `format` | `ReportCreate` | Transport/request envelope; not a displayed object field. |
| `status` | `ReportUpdate`, `ReportResponse`, `ReportDetailResponse`, `ReportListItem` | Report.status → Stateful.status |
| `id` | `ReportResponse`, `ReportDetailResponse`, `ReportListItem` | Report.id |
| `content` | `ReportResponse`, `ReportDetailResponse` | Report.content |
| `citations` | `ReportResponse`, `ReportDetailResponse` | Report.citations |
| `tokens_used` | `ReportResponse`, `ReportDetailResponse`, `ReportListItem` | Report.tokens_used |
| `created_at` | `ReportResponse`, `ReportDetailResponse`, `ReportListItem` | Report.created_at → Timestampable.created_at |
| `report_type` | `ReportDetailResponse`, `ReportListItem` | Report.report_type |
| `chunk_count` | `ReportDetailResponse`, `ReportListItem` | Report.chunk_count |
| `sources` | `ReportDetailResponse` | Report.sources |
| `updated_at` | `ReportDetailResponse`, `ReportListItem` | Report.updated_at → Timestampable.updated_at |
| `items` | `ReportListResponse` | Transport/request envelope; not a displayed object field. |
| `total` | `ReportListResponse` | Transport/request envelope; not a displayed object field. |
| `page` | `ReportListResponse` | Transport/request envelope; not a displayed object field. |
| `page_size` | `ReportListResponse` | Transport/request envelope; not a displayed object field. |
| `success` | `DeleteResponse` | Transport/request envelope; not a displayed object field. |

### Evidence

Source: `app.schemas.evidence_ledger`. Traits: `content/Labelled`, `lifecycle/Timestampable`, `structural/Ownerable`, `core/Classifiable`, `behavioral/Searchable`, `behavioral/Filterable`, `behavioral/Pageable`.

| Field | Pydantic models | Presentation destination |
|---|---|---|
| `claim` | `CaptureItem`, `LedgerEntryRead` | Evidence.claim → Labelled.label (display alias) |
| `summary` | `CaptureItem`, `LedgerEntryRead` | Evidence.summary |
| `source_url` | `CaptureItem`, `LedgerEntryRead` | Evidence.source_url |
| `snippet` | `CaptureItem`, `LedgerEntryRead` | Evidence.snippet |
| `query` | `CaptureItem`, `LedgerEntryRead` | Evidence.query |
| `disposition` | `CaptureItem`, `LedgerEntryRead` | Evidence.disposition → Classifiable.primary_category_id |
| `tags` | `CaptureItem`, `LedgerEntryRead` | Evidence.tags |
| `project_id` | `CaptureRequest`, `LedgerEntryRead`, `PromotionRequest`, `PromotionResponse` | Evidence.project_id |
| `mission_id` | `CaptureRequest`, `LedgerEntryRead`, `DeepSearchEvidenceResponse` | Evidence.mission_id |
| `session_key` | `CaptureRequest`, `LedgerEntryRead`, `DeepSearchEvidenceResponse`, `PromotionRequest`, `PromotionResponse` | Evidence.session_key |
| `entries` | `CaptureRequest`, `CaptureResponse`, `LedgerListResponse`, `LedgerSearchResponse` | Transport/request envelope; not a displayed object field. |
| `project_id` | `NoteUpsertRequest`, `LedgerNoteRead` | Evidence working note (separate from sourced entries).project_id |
| `mission_id` | `NoteUpsertRequest`, `LedgerNoteRead` | Evidence working note (separate from sourced entries).mission_id |
| `session_key` | `NoteUpsertRequest`, `LedgerNoteRead` | Evidence working note (separate from sourced entries).session_key |
| `content` | `NoteUpsertRequest`, `LedgerNoteRead` | Evidence working note (separate from sourced entries).content |
| `tags` | `NoteUpsertRequest`, `LedgerNoteRead` | Evidence working note (separate from sourced entries).tags |
| `id` | `LedgerEntryRead` | Evidence.id |
| `origin` | `LedgerEntryRead` | Evidence.origin |
| `source_id` | `LedgerEntryRead` | Evidence.source_id |
| `source_sighting_count` | `LedgerEntryRead` | Evidence.source_sighting_count |
| `owner_id` | `LedgerEntryRead` | Evidence.owner_id → Ownerable.owner_id (nullable) |
| `workspace_id` | `LedgerEntryRead` | Evidence.workspace_id |
| `created_at` | `LedgerEntryRead` | Evidence.created_at → Timestampable.created_at |
| `updated_at` | `LedgerEntryRead` | Evidence.updated_at → Timestampable.updated_at |
| `id` | `LedgerNoteRead` | Evidence working note (separate from sourced entries).id |
| `note_key` | `LedgerNoteRead` | Evidence working note (separate from sourced entries).note_key |
| `origin` | `LedgerNoteRead` | Evidence working note (separate from sourced entries).origin |
| `owner_id` | `LedgerNoteRead` | Evidence working note (separate from sourced entries).owner_id |
| `workspace_id` | `LedgerNoteRead` | Evidence working note (separate from sourced entries).workspace_id |
| `created_at` | `LedgerNoteRead` | Evidence working note (separate from sourced entries).created_at |
| `updated_at` | `LedgerNoteRead` | Evidence working note (separate from sourced entries).updated_at |
| `count` | `CaptureResponse` | Transport/request envelope; not a displayed object field. |
| `schema_version` | `DeepSearchEvidenceRequest` | Transport/request envelope; not a displayed object field. |
| `deepsearch_job_id` | `DeepSearchEvidenceRequest`, `DeepSearchEvidenceResponse` | Transport/request envelope; not a displayed object field. |
| `status` | `DeepSearchEvidenceResponse`, `PromotionResponse` | Transport/request envelope; not a displayed object field. |
| `entry_ids` | `DeepSearchEvidenceResponse` | Transport/request envelope; not a displayed object field. |
| `entry_count` | `DeepSearchEvidenceResponse`, `PromotionResponse` | Transport/request envelope; not a displayed object field. |
| `notes` | `LedgerListResponse` | Transport/request envelope; not a displayed object field. |
| `entry_total` | `LedgerListResponse` | Transport/request envelope; not a displayed object field. |
| `note_total` | `LedgerListResponse` | Transport/request envelope; not a displayed object field. |
| `page` | `LedgerListResponse`, `LedgerSearchResponse` | Transport/request envelope; not a displayed object field. |
| `page_size` | `LedgerListResponse`, `LedgerSearchResponse` | Transport/request envelope; not a displayed object field. |
| `total` | `LedgerSearchResponse` | Transport/request envelope; not a displayed object field. |
| `title` | `PromotionRequest`, `PromotionResponse` | Transport/request envelope; not a displayed object field. |
| `target` | `PromotionRequest`, `PromotionResponse` | Transport/request envelope; not a displayed object field. |
| `report_id` | `PromotionResponse` | Transport/request envelope; not a displayed object field. |
| `document_id` | `PromotionResponse` | Transport/request envelope; not a displayed object field. |
| `note_count` | `PromotionResponse` | Transport/request envelope; not a displayed object field. |

### Nested document records

| Model.field | Presentation destination |
|---|---|
| `app.schemas.document_status.DocumentProcessingStatusRead.document_id` | Document.processing_events[].document_id |
| `app.schemas.document_status.DocumentProcessingStatusRead.stage` | Document.processing_events[].stage |
| `app.schemas.document_status.DocumentProcessingStatusRead.status` | Document.processing_events[].status |
| `app.schemas.document_status.DocumentProcessingStatusRead.message` | Document.processing_events[].message |
| `app.schemas.document_status.DocumentProcessingStatusRead.details` | Document.processing_events[].details |
| `app.schemas.document_status.DocumentProcessingStatusRead.id` | Document.processing_events[].id |
| `app.schemas.document_status.DocumentProcessingStatusRead.created_at` | Document.processing_events[].created_at |
| `app.schemas.document_status.DocumentProcessingStatusRead.updated_at` | Document.processing_events[].updated_at |
| `app.schemas.tag.DocumentTagRead.document_id` | Document.tags[].document_id |
| `app.schemas.tag.DocumentTagRead.tag_id` | Document.tags[].tag_id |
