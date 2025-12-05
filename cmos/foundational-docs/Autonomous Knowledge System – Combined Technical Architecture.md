Autonomous Knowledge System – Combined Technical Architecture
0) Executive Summary
This architecture unifies three distinct services—DeepSearch, Tracelab, and PEDR—into a single, autonomous knowledge system. The system's purpose is to automate the full research lifecycle: from external discovery (DeepSearch) to structured, traceable storage (Tracelab), to governance-aware internal retrieval (PEDR).

The system operates as a data pipeline:

DeepSearch (The Researcher): An autonomous agent that ingests a mission, scours the public web, and synthesizes its findings.

Tracelab (The Library): A research repository that serves as the "landing pad" for the agent. It ingests the agent's structured output, validates it against quality gates, and stores it in relational (PostgreSQL) and vector (Qdrant) databases.

PEDR (The Catalog): An internal search engine that indexes the contents of Tracelab (its projects, insights, and documents).

This approach turns the "restrictive" manual schemas into the structured output target for the agent. This allows the agent's work to be automatically validated, stored, and made searchable, creating a virtuous, self-populating knowledge base.

1) Goals / Non-Goals
Goals
Automate Research-to-Protocol: Create a fully agent-driven pipeline that turns a research question into a structured, validated, and stored knowledge asset.

Create a Virtuous Knowledge Loop: Use the DeepSearch agent to populate the Tracelab repository, and use the PEDR service to make that repository searchable by the agent itself for future missions.

Maintain Modularity: Allow each of the three services (DS, Tracelab, PEDR) to be developed, deployed, and scaled independently.

Enforce Quality via API: Use the Tracelab schemas and Pydantic validators as the API contract to enforce quality on the agent's output.

Support Hybrid Search: Provide RAG-style search over recent agent findings (via Tracelab) and deep, protocol-aware search over the entire internal catalog (via PEDR).

Non-Goals
Monolithic Application: This is not a single, tightly-coupled app. It is a system of three interoperable services.

Real-time Ingestion: Ingestion from DeepSearch to Tracelab is a discrete, job-based event. Indexing from Tracelab to PEDR can be asynchronous (e.g., scheduled nightly or via a webhook).

Replacing the User: The system is an "autonomous assistant" that prepares research for a human, not a final decision-maker.

2) System Overview
The diagram below shows the flow of data. The DeepSearch agent is the "write" engine, the Tracelab repository is the "storage" layer, and PEDR is the "read" engine for internal knowledge.

+----------------+      +------------------+
| User / CLI     | ---> | DeepSearch Agent |
+----------------+      +------------------+
     |   ^                     |       |
     |   | (Internal Search)   |       | (External Research)
     |   |                     v       v
     |   |               +-----------+ +---------------+
     |   |               | PEDR API  | | Web Search    |
     |   |               | (Layer 2) | | (Tavily, etc) |
     |   +---------------+           +---------------+
     |                               |
     | (Agent Writes Data)           |
     v                               v
+--------------------------------------------------------+
| Tracelab (Research Repository) API                     |
| (POST /api/missions, POST /api/documents)              |
| [Quality Gates & Pydantic Validation Layer]            |
+------------------+-------------------------------------+
                   | (Writes)
         +---------v---------+      +--------------------+
         | PostgreSQL DB     |      | Qdrant Vector DB   |
         | (Metadata, Docs,  |      | (Chunks, Embeddings|
         |  Insights, Missions)|      |  for RAG)          |
         +-------------------+      +--------------------+
                   ^ (Indexes)            ^ (Indexes)
                   |                      |
+------------------+----------------------+----------------+
| PEDR (Protocol-Enhanced Deep Research) Service          |
| (Indexes Tracelab DB to build its 6-layer catalog)      |
+---------------------------------------------------------+
3) Core Components & Integration
1. DeepSearch (Agent Service)
Purpose: The "Researcher." Executes a Mission Protocol by searching the web and synthesizing findings.

Integration (Write): This agent is the primary client of the Tracelab API. Its final "Report Generator" node is re-configured to:

Generate JSON payloads that strictly adhere to the Tracelab schemas (missions, documents, insights, document_chunks).

POST this structured data to the Tracelab API (e.g., POST /api/missions, POST /api/documents).

Integration (Read): Before starting a new web search, the agent's first step is to query the PEDR API (POST /api/v1/search) to see if the knowledge already exists internally.

2. Tracelab (Research Repository Service)
Purpose: The "Library." Provides persistent, validated storage and a RAG API for all research generated by the DeepSearch agent.

Integration (Ingestion): Exposes the API endpoints (/api/missions, /api/documents, etc.) that the DeepSearch agent writes to.

Core Function: This service's "Quality Gates" and Pydantic models are no longer for humans; they are the automated validation layer for agent-submitted data. If an agent's submission fails validation (e.g., "unresolved_contradictions"), the API returns a 422 Unprocessable Entity error, which could trigger a "correction loop" in the agent.

Core Function: Provides the /api/search/rag endpoint for simple, RAG-based queries on its own vector store.

3. PEDR (Internal Search Service)
Purpose: The "Catalog." Provides a sophisticated, multi-layer hybrid search interface for the entire knowledge base stored in Tracelab.

Integration (Read/Index): The PEDR service's "Ingestion & Catalog Builder" is modified. Instead of watching a filesystem for YAML manifests, it connects directly to the Tracelab PostgreSQL database.

New Ingestion Flow:

On a schedule (e.g., every hour) or via a webhook from Tracelab.

PEDR reads the projects, documents, and insights tables from the Tracelab database.

It normalizes this data into its own protocol_catalog (SQLite) and builds its hnswsqlite vector index and NetworkX graph.

Integration (Serve): Exposes its /api/v1/search endpoint to be used by both the human user (for deep research) and the DeepSearch agent (for checking existing work).

4) Canonical Flows
Flow: Agent-Driven External Research (The "Write" Path)
User gives DeepSearch a mission: "Research passwordless auth."

DeepSearch queries PEDR: POST /api/v1/search {"query": "passwordless auth"}.

PEDR returns 0 results.

DeepSearch executes its web-search and synthesis loops.

DeepSearch generates structured JSON for the mission, documents, chunks, and insights.

DeepSearch POSTs this data to the Tracelab API (e.g., POST /api/missions).

Tracelab API validates the payload using its Pydantic models and "Quality Gates".

Tracelab saves the data to its PostgreSQL and Qdrant databases.

(Later) The PEDR service's scheduled job runs, discovers the new mission in Tracelab's DB, and indexes it.

Flow: Human-Driven Internal Research (The "Read" Path)
User wants to find the previous research.

User queries PEDR: POST /api/v1/search {"query": "passwordless auth"}.

PEDR now finds the match (indexed from Tracelab) and returns a ranked list, e.g., urn:research:mission-001.

The user's UI can then use this URN to fetch the full report from the Tracelab API: GET /api/missions/mission-001.

Flow: RAG-Based Query (The "Quick Answer" Path)
User (or an app) just wants a quick answer, not a full protocol.

User queries Tracelab: POST /api/search/rag {"query": "what did users say about magic links?"}.

Tracelab uses its own Qdrant RAG pipeline to get a direct, AI-generated answer based on the chunks stored from the agent's research.