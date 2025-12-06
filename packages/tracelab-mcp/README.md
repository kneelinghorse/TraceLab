# TraceLab MCP Server

MCP (Model Context Protocol) server that enables AI agents to perform complete research-to-output loops against TraceLab's knowledge base.

## Features

- **8 research tools** for semantic search, collection management, and synthesis
- **Full research workflow** - search, collect, synthesize
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

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TRACELAB_API_URL` | TraceLab API base URL | Yes (default: `http://localhost:8000`) |
| `TRACELAB_TOKEN` | JWT authentication token | One of token/apiKey |
| `TRACELAB_API_KEY` | API key for authentication | One of token/apiKey |

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

4. **Synthesize the findings**
   ```
   synthesize(collection_id="...", prompt="Summarize the top 5 ML best practices", format="markdown")
   ```

5. **Export for reference**
   ```
   export_collection(collection_id="...")
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
