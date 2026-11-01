# Sprint 23 Retrospective: MCP Agent Usability

**Sprint Period:** December 2025
**Focus:** Make TraceLab MCP useful for agents - fix research_depth visibility, add document content retrieval, add update_mission tool, improve tool discoverability

## Summary

Sprint 23 focused on making the TraceLab MCP server more usable for AI agents. All five planned missions were completed successfully.

## Completed Missions

### B23.1: Add research_depth to TypeScript MCP Package ✓
**Objective:** The TypeScript MCP at packages/tracelab-mcp/ was missing research_depth entirely.

**Changes:**
- Added `research_depth?: 'baseline' | 'deep' | 'alpha'` to Mission, MissionCreate, and MissionUpdate interfaces in api-client.ts
- Added research_depth to create_mission tool inputSchema with enum and clear tier descriptions
- Added research_depth to submit_mission tool inputSchema for override capability
- Added research_depth to zod schemas (CreateMissionInput, SubmitMissionInput)
- Updated handleCreateMission to pass research_depth to API
- Updated handleSubmitMission to support research_depth override
- Updated handleGetMission to include research_depth in response

**Impact:** Agents can now create missions with specific research depth tiers and see the depth when retrieving mission details.

---

### B23.2: Add update_mission MCP Tool ✓
**Objective:** Agents could only create missions, not edit them.

**Changes:**
- Added update_mission tool definition with full inputSchema supporting all editable fields
- Added UpdateMissionInput zod schema for validation
- Implemented handleUpdateMission handler that updates missions via API
- Registered update_mission in MCP server tool switch statement
- Updated header comment to reflect 22 tools

**Impact:** Agents can now modify existing missions including changing research_depth before submission.

---

### B23.3: Add get_document_content MCP Tool ✓
**Objective:** Agents couldn't read document text through MCP.

**Changes:**
- Added Document, DocumentChunk, DocumentChunksResponse interfaces to api-client.ts
- Added getDocument() and getDocumentChunks() methods to TraceLabClient
- Added get_document_content tool with pagination support
- Implemented handleGetDocumentContent handler with:
  - Optional metadata retrieval (name, file_type, word_count, chunk_count)
  - Chunk pagination for large documents
  - Continuation hints for multi-page documents
- Updated header comment to reflect 23 tools

**Impact:** Agents can now read full document content from the knowledge base, enabling more comprehensive research workflows.

---

### B23.4: Improve MCP Tool Descriptions for Discoverability ✓
**Objective:** Tool descriptions were technically accurate but agents struggled to find tools or understand parameters.

**Changes:**
- Rewrote search_knowledge description with action verb, examples, and related tools
- Enhanced create_mission with detailed parameter examples and research_depth tier explanations
- Improved list_missions with status value explanations
- Updated get_mission to explain returned fields and mention related tools
- Enhanced update_mission and submit_mission with clear research_depth guidance
- Added concrete examples to all complex parameters

**Key Pattern Applied:**
- All descriptions start with clear action verbs (Find, Create, Browse, Retrieve, Modify, Queue, Check, Read)
- research_depth consistently explains: BASELINE (~5 min), DEEP (~15-30 min), ALPHA (~1+ hour)
- All tools mention related tools for discoverability
- Parameters explain how to get required values

**Impact:** Agents should now be able to discover tools more easily and understand when to use each research_depth tier.

---

### B23.5: Add Research Depth to Edit Mission UI ✓
**Objective:** Only the create form had research_depth; editing required programmatic access.

**Changes:**
- Added `research_depth?: ResearchDepth` to ApiMissionUpdate interface
- Added editResearchDepth state to mission detail page edit mode
- Added Research Depth dropdown selector with tier descriptions:
  - Baseline - Quick scan (~5 min)
  - Deep - Comprehensive analysis (~15-30 min)
  - Alpha - Exhaustive research (~1+ hour)
- Added research_depth badge display in view mode with color coding:
  - Alpha: purple (⚡)
  - Deep: blue (🔍)
  - Baseline: gray (📌)
- Updated handleSaveEdit to persist research_depth to API

**Impact:** Users can now see and modify research_depth directly in the mission UI.

---

## Key Metrics

| Metric | Before Sprint | After Sprint |
|--------|---------------|--------------|
| MCP Tools | 21 | 23 |
| Mission fields editable via MCP | 6 | 8 (added research_depth, update capability) |
| Document content accessible via MCP | No | Yes |
| research_depth visible in UI | Create only | Create + Edit + View |

## Learnings

1. **TypeScript MCP is primary agent interface** - B23.1's context clarified that packages/tracelab-mcp/ is what agents actually use, not the Python MCP server. Future MCP improvements should target TypeScript first.

2. **Tool descriptions matter for discoverability** - Agents struggle with terse descriptions. Adding examples, related tool mentions, and explaining "why" (not just "what") significantly improves usability.

3. **Pagination is essential for large content** - The get_document_content implementation showed that chunked retrieval with continuation hints is necessary for agent workflows that need to process large documents.

4. **research_depth needs consistent messaging** - Established pattern: BASELINE (~5 min), DEEP (~15-30 min), ALPHA (~1+ hour) with use case guidance. This should be standardized across all surfaces.

## Sprint 24 Backlog Draft

Based on this sprint's work and observed gaps:

1. **B24.1: Add list_documents MCP Tool** - Agents can search chunks but can't browse documents by project. Add list_documents tool with project/type filtering.

2. **B24.2: Add Mission Lifecycle Tools** - Add cancel_mission, retry_mission tools for workflow control.

3. **B24.3: MCP Error Response Standardization** - Current error responses vary. Standardize error format with actionable suggestions.

4. **B24.4: Add Mission Progress Streaming** - For long-running alpha missions, add progress streaming or polling endpoint.

5. **B24.5: Tool Usage Documentation** - Create agent-facing documentation showing common workflows (create mission → check status → read results).

6. **B24.6: Sprint 24 Retrospective**

---

## Conclusion

Sprint 23 successfully improved MCP usability for agents. The key deliverables - research_depth visibility, update_mission capability, document content retrieval, and improved descriptions - should make agent-driven research workflows significantly more effective.

The sprint validated that small usability improvements (clearer descriptions, better examples, completing CRUD operations) have outsized impact on agent effectiveness.
