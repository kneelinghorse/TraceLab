# Sprint 06: CLI & Document Repository UI

**Sprint Goal:** Make TraceLab fully functional with agent-first CLI, document management UI, RAG search interface, and Mission Protocol integration.

**Duration:** 2025-11-10 to 2025-11-20 (10 days)

**Status:** Planned

---

## Overview

Sprint 06 transforms TraceLab from backend-only APIs into a complete functional research repository. Both agents and humans will be able to upload documents, search semantically, track research missions, collect evidence, and export reports with full traceability.

## Success Criteria

1. ✅ CLI provides complete CRUD operations for all resources with token auth and JSON output
2. ✅ Document library UI allows upload, browse, organize with processing status
3. ⏳ RAG search UI delivers query, results, synthesis with citations
4. ⏳ Mission UI is readable, functional, and supports evidence linking
5. ⏳ Report export generates MD/PDF/DOCX with full traceability
6. ⏳ Integration API connects external Mission Protocol MCP server
7. ⏳ End-to-end workflows validated for agents and humans

## Missions

### B6.1: CLI Implementation ✅ (Current)
**Status:** Partially complete (code written, needs agent verification)  
**Focus:** Agent-first CLI with Click framework, token auth, JSON output

**Deliverables:**
- cli/ directory with complete command structure
- Token storage in ~/.tracelab/token
- JSON output mode (--json flag)
- docs/cli_architecture.md and docs/cli_usage.md
- Pytest suite

**Agent Notes:**
- CLI code already written in cli/ directory
- Verify functionality and fix any issues
- Add missing commands if needed
- Ensure all tests pass

---

### B6.2: Document Library UI ✅ (Queued)
**Status:** Partially complete (pages written, needs agent verification)  
**Focus:** Document upload, browse, and management interface

**Deliverables:**
- /documents - List page with filters
- /documents/upload - Multi-file upload with drag-drop
- /documents/[id] - Detail page with processing status
- Navigation component with logout
- API client and types

**Agent Notes:**
- UI pages already in frontend/src/pages/documents/
- Verify rendering and functionality
- Fix any TypeScript errors
- Test upload and processing flows

---

### B6.3: RAG Search UI (Queued)
**Focus:** Semantic search and RAG query interface

**Deliverables:**
- /search page with query input
- Semantic search results display
- RAG synthesis with citations
- Evidence quick-add to missions
- Search API client

---

### B6.4: Mission UI Overhaul (Queued)
**Focus:** Fix readability and functionality of existing Mission Protocol UI

**Deliverables:**
- Readable light/dark theme
- Evidence cards with source documents
- Quality gate visualization
- Evidence linking from search page

---

### B6.5: Report Export System (Queued)
**Focus:** Generate formatted reports from missions

**Deliverables:**
- Export service supporting MD/PDF/DOCX
- Report templates with citations
- CLI and UI export commands
- Full traceability in reports

---

### B6.6: Integration API (Queued)
**Focus:** Connect external Mission Protocol MCP server

**Deliverables:**
- Project lookup/create endpoint
- Mission creation from YAML
- Status polling for external tools
- Integration documentation

---

### B6.7: Sprint Retrospective (Queued)
**Focus:** Validate workflows and generate sprint report

**Deliverables:**
- End-to-end testing (agent + human)
- Sprint 06 retrospective report
- Sprint 07 backlog seeding

---

## Integration Vision

**Mission Protocol MCP** → generates research mission YAML  
↓  
**TraceLab** → collects evidence via RAG search  
↓  
**Reports** → MD/PDF/DOCX with full traceability

**Example Workflow:**
1. Agent: "Research semantic search for MCP Hub fork"
2. Mission Protocol MCP creates research.deep-research-technical YAML
3. Agent uses TraceLab CLI to query 1000s of documents
4. Agent links relevant chunks as evidence
5. TraceLab synthesizes findings
6. Export MD/PDF report with full citation chain

---

## Dependencies

**External:**
- Mission Protocol MCP server (26 domain packs available)
- Backend APIs operational (Sprints 01-05 complete)
- Auth system working (B5.2 complete)
- Railway deployment live (B5.1 complete)

**Internal:**
- B6.1 → B6.2 (CLI provides baseline for UI)
- B6.2 → B6.3 (documents must exist to search)
- B6.3 → B6.4 (search results link to mission evidence)
- B6.4 → B6.5 (missions export as reports)
- B6.5 → B6.6 (reports flow back to Mission Protocol)
- All → B6.7 (retrospective validates everything)

---

## Notes for Agents

**B6.1 and B6.2 Status:**
- Code already written and committed
- Located in cli/ and frontend/src/pages/documents/
- Agent should verify, test, and fix any issues
- Don't start from scratch - validate existing work

**For B6.3-B6.7:**
- Build on existing patterns from B6.1-B6.2
- Use AuthGate for all UI pages
- Follow CLI patterns for new commands
- Maintain JSON output consistency

---

**Last Updated:** 2025-11-10  
**Next Review:** After B6.1 agent verification

