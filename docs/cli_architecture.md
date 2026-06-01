# TraceLab CLI Architecture

## Overview

The TraceLab CLI is designed with **agents as the primary user**, with human usability as a strong secondary concern. The CLI provides complete CRUD access to all TraceLab resources (projects, documents, missions, search) with consistent patterns, JSON output modes, and robust error handling.

## Design Principles

### 1. Agent-First Design

**Key Requirements:**
- **Deterministic output**: Exit codes, JSON format, predictable errors
- **Parseable errors**: Structured error objects, not plain text
- **Batch-friendly**: Commands support piping, bulk operations
- **Non-interactive**: No prompts, all inputs via flags/args
- **Stateless auth**: Token stored in `~/.tracelab/token`, automatic inclusion

**Example:**
```bash
# Human use - readable output
$ tracelab projects list
✓ Found 3 projects:
  - Research Archive (proj_abc123)
  - Tech History (proj_def456)
  - AI Papers (proj_ghi789)

# Agent use - JSON output
$ tracelab projects list --json
{"projects": [{"id": "proj_abc123", "name": "Research Archive"}, ...]}
```

### 2. Consistent Command Structure

All commands follow the pattern: `tracelab <resource> <action> [arguments] [flags]`

**Resources:**
- `auth` - Authentication management
- `projects` - Project CRUD
- `documents` - Document upload/management  
- `search` - Semantic search
- `rag` - RAG query with LLM synthesis
- `missions` - Mission Protocol CRUD
- `config` - CLI configuration

**Common Actions:**
- `list` - List resources (supports filtering, pagination)
- `get` - Retrieve single resource by ID
- `create` - Create new resource
- `update` - Update existing resource
- `delete` - Delete resource

### 3. Error Handling

**Exit Codes:**
- `0` - Success
- `1` - General error (network, API failure)
- `2` - Invalid arguments
- `3` - Authentication error
- `4` - Resource not found
- `5` - Permission denied

**Error Format (JSON mode):**
```json
{
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Invalid credentials",
    "details": {
      "reason": "Token expired",
      "suggestion": "Run 'tracelab auth login' to refresh"
    }
  }
}
```

**Error Format (Human mode):**
```
✗ Error: Authentication failed
  Reason: Token expired
  Suggestion: Run 'tracelab auth login' to refresh your token
```

### 4. Token-Based Authentication

**Flow:**
1. User runs `tracelab auth login --username <user> --password <pass>`
2. CLI calls `/api/v1/auth/login`, receives JWT
3. Token stored in `~/.tracelab/token` (chmod 600)
4. All subsequent commands auto-include `Authorization: Bearer <token>`
5. Token refresh handled automatically when near expiration

**Token Storage Location:**
```
~/.tracelab/
├── token          # JWT access token
├── config.json    # User preferences (API URL, defaults)
└── history.jsonl  # Command history (optional)
```

**Token Format:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_at": "2025-11-11T12:00:00Z"
}
```

## Command Reference

### Auth Commands

```bash
# Login
tracelab auth login --username <user> --password <pass>
tracelab auth login --username <user>  # prompts for password

# Check authentication status
tracelab auth status
tracelab auth status --json

# Refresh token
tracelab auth refresh

# Logout
tracelab auth logout
```

### Project Commands

```bash
# List projects
tracelab projects list
tracelab projects list --json

# Get project
tracelab projects get <project-id>
tracelab projects get <project-id> --json

# Create project
tracelab projects create --name "Tech History" --description "Historical tech research"
tracelab projects create --name "..." --json

# Update project
tracelab projects update <project-id> --name "New Name"

# Delete project
tracelab projects delete <project-id>
tracelab projects delete <project-id> --confirm  # skip prompt
```

### Document Commands

```bash
# Upload document
tracelab documents upload <project-id> <file-path>
tracelab documents upload <project-id> <file-path> --process  # auto-process
tracelab documents upload <project-id> <file-path> --json

# Batch upload
tracelab documents upload <project-id> ./reports/*.pdf --batch --json

# List documents
tracelab documents list --project-id <project-id>
tracelab documents list --status processed --page 2 --json

# Get document
tracelab documents get <document-id>
tracelab documents get <document-id> --json

# Process document
tracelab documents process <document-id>
tracelab documents process <document-id> --wait  # block until complete

# Check processing status
tracelab documents status <document-id>
tracelab documents status <document-id> --json

# Delete document
tracelab documents delete <document-id>
```

### Search Commands

```bash
# Semantic search
tracelab search <project-id> "query text"
tracelab search <project-id> "query text" --top-k 10 --json

# RAG query (with LLM synthesis)
tracelab rag query <project-id> "question?"
tracelab rag query <project-id> "question?" --model gpt-5.2 --json

# Search with filters
tracelab search <project-id> "query" --document-type pdf --after 2024-01-01
```

### Mission Commands

```bash
# List missions
tracelab missions list <project-id>
tracelab missions list <project-id> --status draft --json

# Get mission
tracelab missions get <mission-id>
tracelab missions get <mission-id> --json

# Create mission
tracelab missions create <project-id> --title "Research Question" --yaml mission.yaml
tracelab missions create <project-id> --title "..." --json

# Import mission from YAML
tracelab missions import <project-id> mission.yaml
tracelab missions import <project-id> mission.yaml --promote  # promote to complete

# Add evidence
tracelab missions add-evidence <mission-id> <chunk-id>
tracelab missions add-evidence <mission-id> <chunk-id> --note "Supporting data"

# Update synthesis
tracelab missions update <mission-id> --synthesis "Key findings..."

# Run quality gates
tracelab missions validate <mission-id>
tracelab missions validate <mission-id> --json

# Export mission
tracelab missions export <mission-id> --format md
tracelab missions export <mission-id> --format pdf --output report.pdf
tracelab missions export <mission-id> --format docx --json

# Delete mission
tracelab missions delete <mission-id>
```

### Config Commands

```bash
# Show configuration
tracelab config show
tracelab config show --json

# Set API URL
tracelab config set api-url https://api.tracelab.aquex.ai

# Set default project
tracelab config set default-project proj_abc123

# Reset configuration
tracelab config reset
```

### Utility Commands

```bash
# Show version
tracelab version
tracelab version --json

# Health check
tracelab health
tracelab health --json

# Show help
tracelab --help
tracelab <resource> --help
tracelab <resource> <action> --help
```

## Global Flags

All commands support these global flags:

- `--json` - Output in JSON format (for agents)
- `--quiet` - Suppress non-essential output
- `--verbose` - Enable debug logging
- `--api-url <url>` - Override API base URL
- `--token <token>` - Override stored token
- `--no-color` - Disable color output

## JSON Output Mode

When `--json` flag is present:
1. All output is valid JSON
2. Success format:
   ```json
   {
     "success": true,
     "data": { ... },
     "meta": {
       "timestamp": "2025-11-10T12:00:00Z",
       "command": "projects list"
     }
   }
   ```
3. Error format:
   ```json
   {
     "success": false,
     "error": {
       "code": "...",
       "message": "...",
       "details": { ... }
     }
   }
   ```
4. Progress indicators disabled
5. Colors disabled

## Agent Workflow Examples

### Example 1: Upload and Query

```bash
# Agent creates project
PROJECT_ID=$(tracelab projects create --name "Tech Research" --json | jq -r '.data.id')

# Agent uploads documents
for file in reports/*.pdf; do
  tracelab documents upload $PROJECT_ID "$file" --process --json
done

# Agent queries
RESULTS=$(tracelab rag query $PROJECT_ID "What were the key innovations?" --json)
echo "$RESULTS" | jq -r '.data.answer'
```

### Example 2: Mission Evidence Collection

```bash
# Agent creates mission
MISSION_ID=$(tracelab missions create $PROJECT_ID --title "ARPANET Research" --json | jq -r '.data.id')

# Agent searches for evidence
SEARCH_RESULTS=$(tracelab search $PROJECT_ID "ARPANET protocols" --json)

# Agent adds top 3 results as evidence
echo "$SEARCH_RESULTS" | jq -r '.data.results[:3][].chunk_id' | while read CHUNK_ID; do
  tracelab missions add-evidence $MISSION_ID $CHUNK_ID --json
done

# Agent exports report
tracelab missions export $MISSION_ID --format md --output report.md
```

### Example 3: Batch Processing

```bash
# Agent processes multiple documents and collects status
DOCUMENTS=$(tracelab documents upload $PROJECT_ID ./corpus/*.pdf --batch --json)

# Extract document IDs
DOC_IDS=$(echo "$DOCUMENTS" | jq -r '.data.documents[].id')

# Poll status until all complete
for DOC_ID in $DOC_IDS; do
  while true; do
    STATUS=$(tracelab documents status $DOC_ID --json | jq -r '.data.status')
    if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then
      break
    fi
    sleep 2
  done
done
```

## Implementation Details

### Technology Stack

- **Framework**: Click (Python CLI framework)
- **HTTP Client**: httpx (async-capable)
- **JSON**: stdlib json module
- **Config**: JSON file in `~/.tracelab/`
- **Progress**: rich (progress bars, spinners)
- **Colors**: rich (color support detection)

### File Structure

```
cli/
├── __init__.py
├── main.py              # Entry point, Click app
├── commands/
│   ├── __init__.py
│   ├── auth.py          # Auth commands
│   ├── projects.py      # Project commands
│   ├── documents.py     # Document commands
│   ├── search.py        # Search commands
│   ├── missions.py      # Mission commands
│   └── config.py        # Config commands
├── utils/
│   ├── __init__.py
│   ├── auth.py          # Token management
│   ├── api.py           # HTTP client wrapper
│   ├── config.py        # Config file management
│   ├── output.py        # Output formatting
│   └── errors.py        # Error handling
└── tests/
    ├── test_auth.py
    ├── test_projects.py
    └── ...
```

### Configuration File Schema

```json
{
  "version": "1.0.0",
  "api": {
    "base_url": "http://localhost:8000",
    "timeout": 30
  },
  "defaults": {
    "project_id": null,
    "output_format": "human"
  },
  "preferences": {
    "color": true,
    "progress": true
  }
}
```

## Testing Strategy

### Unit Tests
- Test each command in isolation
- Mock API responses
- Validate JSON output format
- Test error handling

### Integration Tests
- Test against real API (test environment)
- Validate end-to-end workflows
- Test token refresh flow
- Test batch operations

### Agent Tests
- Simulate agent workflows
- Test JSON parsing reliability
- Validate exit codes
- Test non-interactive mode

## Installation

```bash
# Development install
cd TraceLab
pip install -e .

# Production install
pip install tracelab-cli

# Verify installation
tracelab version
```

## Future Enhancements

### Phase 2 (Sprint 07)
- Shell completion (bash, zsh, fish)
- Interactive mode (`tracelab shell`)
- Watch mode for document processing
- Built-in query templates

### Phase 3 (Sprint 08)
- Plugin system for custom commands
- Batch file support (YAML workflow definitions)
- Remote config sync
- Team collaboration features

## References

- Click Documentation: https://click.palletsprojects.com/
- httpx Documentation: https://www.python-httpx.org/
- Rich Documentation: https://rich.readthedocs.io/
- JWT Best Practices: https://datatracker.ietf.org/doc/html/rfc8725
