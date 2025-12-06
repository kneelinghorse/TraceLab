# TraceLab MCP Server

MCP (Model Context Protocol) server that enables AI agents to perform complete research-to-output loops against TraceLab's knowledge base.

## Features

- **13 research tools** for semantic search, collection management, synthesis, report generation, and document upload
- **Full research workflow** - search, collect, synthesize, persist
- **Persistent reports** - save synthesis results as named artifacts that survive across sessions
- **Multiple auth methods** - JWT tokens or API keys
- **Claude Code compatible** - works out of the box with Claude Desktop

## Installation

### Option 1: npx (recommended)

```bash
npx @tracelab/mcp-server
```

### Option 2: Global install

```bash
npm install -g @tracelab/mcp-server
tracelab-mcp
```

### Option 3: From source

```bash
git clone https://github.com/your-org/tracelab.git
cd tracelab/packages/tracelab-mcp
npm install
npm run build
npm start
```

## Configuration

### Generating an API Key (Recommended)

API keys are the recommended authentication method for MCP servers - they don't expire like JWT tokens and don't require periodic refresh.

**Step 1: Get a JWT token**
```bash
curl -X POST https://your-tracelab-instance.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your-username", "password": "your-password"}'
```

**Step 2: Create an API key**
```bash
curl -X POST https://your-tracelab-instance.com/api/v1/auth/api-keys \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "MCP Server"}'
```

The response contains your API key - **save it immediately**, as it's only shown once:
```json
{
  "id": "uuid",
  "name": "MCP Server",
  "key": "tl_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",  // Save this!
  "key_prefix": "tl_a1b2c3d4",
  "created_at": "2025-12-06T00:00:00Z",
  "expires_at": null
}
```

**API Key Format**: `tl_` prefix followed by 32 alphanumeric characters.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TRACELAB_API_URL` | TraceLab API base URL | Yes (default: `http://localhost:8000`) |
| `TRACELAB_API_KEY` | API key for authentication (recommended) | One of apiKey/token |
| `TRACELAB_TOKEN` | JWT authentication token | One of apiKey/token |

### Claude Desktop Configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tracelab": {
      "command": "npx",
      "args": ["@tracelab/mcp-server"],
      "env": {
        "TRACELAB_API_URL": "https://your-tracelab-instance.com",
        "TRACELAB_API_KEY": "your-api-key"
      }
    }
  }
}
```

Or with JWT token:

```json
{
  "mcpServers": {
    "tracelab": {
      "command": "npx",
      "args": ["@tracelab/mcp-server"],
      "env": {
        "TRACELAB_API_URL": "https://your-tracelab-instance.com",
        "TRACELAB_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

### Claude Code Configuration

For Claude Code CLI, add to your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "tracelab": {
      "command": "npx",
      "args": ["@tracelab/mcp-server"],
      "env": {
        "TRACELAB_API_URL": "https://your-tracelab-instance.com",
        "TRACELAB_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Available Tools

### 1. search_knowledge

Search for relevant knowledge chunks using semantic search.

```
Parameters:
- query (required): The search query - can be a question or topic
- project_id: Filter by project UUID
- limit: Maximum results (1-50, default: 10)
- tags: Filter by tags (OR semantics)
```

### 2. list_projects

List all available projects in TraceLab.

```
Parameters:
- page: Page number (1-indexed, default: 1)
- page_size: Results per page (1-100, default: 20)
- search: Search by project name
```

### 3. list_collections

List all research collections.

```
Parameters: none
```

### 4. get_collection

Get detailed information about a collection including all its chunks.

```
Parameters:
- collection_id (required): UUID of the collection
```

### 5. export_collection

Export a collection as a markdown document.

```
Parameters:
- collection_id (required): UUID of the collection
```

### 6. create_collection

Create a new collection to organize research chunks.

```
Parameters:
- name (required): Name for the collection (max 255 chars)
- description: Optional description (max 2000 chars)
```

### 7. add_to_collection

Add a knowledge chunk to a collection.

```
Parameters:
- collection_id (required): UUID of the collection
- chunk_id (required): UUID of the chunk (from search results)
- notes: Optional notes about relevance
```

### 8. synthesize

Generate a summary or report from collected chunks.

```
Parameters:
- collection_id (required): UUID of the collection
- prompt: Custom synthesis prompt
- format: Output format (markdown, summary, report)
```

### 9. create_report

Create a new persistent report by synthesizing content from a collection or specific chunks. Reports are named artifacts that survive across sessions.

```
Parameters:
- title (required): Title for the report (max 255 chars)
- collection_id: UUID of collection to synthesize (mutually exclusive with chunk_ids)
- chunk_ids: Array of chunk UUIDs to synthesize (mutually exclusive with collection_id)
- project_id: UUID of project to associate report with
- prompt: Custom synthesis prompt (max 2000 chars)
- format: Output format (summary, report, bullets, markdown)
```

### 10. list_reports

Browse existing reports with optional filtering.

```
Parameters:
- project_id: Filter by project UUID
- status: Filter by status (draft, final)
- page: Page number (1-indexed, default: 1)
- page_size: Results per page (1-100, default: 20)
```

### 11. get_report

Get full report details including content, citations, and source references.

```
Parameters:
- report_id (required): UUID of the report
```

### 12. export_report

Export a report as markdown text.

```
Parameters:
- report_id (required): UUID of the report
```

### 13. upload_document

Upload a new document to TraceLab for ingestion. The document will be processed through the ingestion pipeline (parsing, PII redaction, chunking, embedding).

```
Parameters:
- name (required): Filename or document name (e.g., "research-paper.pdf")
- content (required): Base64 encoded file content
- content_type (required): MIME type of the file
- project_id (required): UUID of the project to add the document to
- description: Optional description of the document

Supported content types:
- application/pdf (.pdf)
- application/vnd.openxmlformats-officedocument.wordprocessingml.document (.docx)
- application/vnd.openxmlformats-officedocument.presentationml.presentation (.pptx)
- text/csv (.csv)
- application/vnd.openxmlformats-officedocument.spreadsheetml.sheet (.xlsx)
- text/markdown (.md)
- text/plain (.txt)
- application/json (.json)
- application/xml, text/xml (.xml)
- application/x-yaml, text/yaml (.yaml, .yml)
```

## Example Research Workflow

Here's how an AI agent might use these tools to complete a research task:

1. **Search for relevant knowledge**
   ```
   search_knowledge(query="machine learning best practices", limit=20)
   ```

2. **Create a collection for the research**
   ```
   create_collection(name="ML Best Practices Research", description="Gathering best practices for ML deployment")
   ```

3. **Add relevant chunks to the collection**
   ```
   add_to_collection(collection_id="...", chunk_id="...", notes="Key insight about model validation")
   ```

4. **Create a persistent report** (recommended)
   ```
   create_report(
     title="ML Best Practices Summary",
     collection_id="...",
     prompt="Summarize the top 5 ML best practices",
     format="report"
   )
   ```

5. **Retrieve the report later**
   ```
   list_reports(status="final")
   get_report(report_id="...")
   export_report(report_id="...")
   ```

### Alternative: Quick Synthesis (non-persistent)

For ephemeral analysis without saving:

```
synthesize(collection_id="...", prompt="Summarize findings", format="markdown")
```

Or export raw collection:

```
export_collection(collection_id="...")
```

## Example Document Upload Workflow

AI agents can upload documents they discover or generate for later search:

1. **Upload a document** (from base64 content)
   ```
   upload_document(
     name="research-findings.md",
     content="IyBSZXNlYXJjaCBGaW5kaW5ncwoK...",  // base64 encoded
     content_type="text/markdown",
     project_id="uuid-of-project"
   )
   ```

2. **Wait for processing** (optional)
   The document is queued for processing. You can immediately continue working,
   or poll the document status via the API.

3. **Search the new content**
   ```
   search_knowledge(query="findings from uploaded research", project_id="...")
   ```

### Converting files to base64

**In JavaScript/TypeScript:**
```javascript
const content = fs.readFileSync('document.pdf');
const base64 = content.toString('base64');
```

**In Python:**
```python
import base64
with open('document.pdf', 'rb') as f:
    base64_content = base64.b64encode(f.read()).decode('utf-8')
```

**In shell:**
```bash
base64 < document.pdf
```

## Development

### Build

```bash
npm run build
```

### Test

```bash
npm test
```

### Watch mode

```bash
npm run dev
```

## Requirements

- Node.js 18+
- TraceLab API instance with authentication configured

## License

MIT
