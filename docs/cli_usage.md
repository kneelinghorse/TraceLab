# TraceLab CLI Usage Guide

## Installation

### Development Installation

```bash
cd TraceLab
pip install -e .
```

### Production Installation

```bash
pip install tracelab-cli
```

### Verify Installation

```bash
tracelab version
tracelab --help
```

## Quick Start

### 1. Authenticate

```bash
tracelab auth login --username your-username --password your-password
```

Or with password prompt:
```bash
tracelab auth login --username your-username
```

### 2. Create a Project

```bash
tracelab projects create --name "Tech History Research" --description "Historical technology research"
```

### 3. Upload Documents

```bash
# Get project ID from previous command or list
PROJECT_ID="your-project-id"

# Upload and process a document
tracelab documents upload $PROJECT_ID ./reports/report1.pdf --process --wait
```

### 4. Search Documents

```bash
# Semantic search
tracelab search semantic $PROJECT_ID "ARPANET protocols"

# RAG query with LLM synthesis
tracelab rag query $PROJECT_ID "What were the key innovations in ARPANET?"
```

### 5. Create Research Mission

```bash
tracelab missions create $PROJECT_ID --title "ARPANET Research"
```

## Agent Workflows

### Workflow 1: Bulk Document Upload

```bash
#!/bin/bash
PROJECT_ID="proj-abc123"

# Upload all PDFs in directory
for file in ./corpus/*.pdf; do
  echo "Uploading $file..."
  tracelab documents upload $PROJECT_ID "$file" --process --json | jq -r '.data.id'
done
```

### Workflow 2: Research Evidence Collection

```bash
#!/bin/bash
PROJECT_ID="proj-abc123"
QUERY="machine learning breakthroughs"

# Create mission
MISSION_ID=$(tracelab missions create $PROJECT_ID \
  --title "ML Research" \
  --json | jq -r '.data.id')

# Search and collect evidence
RESULTS=$(tracelab search semantic $PROJECT_ID "$QUERY" --json)

# Add top results as evidence
echo "$RESULTS" | jq -r '.data.results[:3][].id' | while read CHUNK_ID; do
  tracelab missions add-evidence $MISSION_ID $CHUNK_ID --json
done

# Export report
tracelab missions export $MISSION_ID --format md --output report.md
```

### Workflow 3: Monitoring Processing Status

```bash
#!/bin/bash
DOCUMENT_ID="doc-xyz789"

# Poll until processing complete
while true; do
  STATUS=$(tracelab documents status $DOCUMENT_ID --json | jq -r '.data.processed')
  if [[ "$STATUS" == "true" ]]; then
    echo "Processing complete!"
    break
  fi
  echo "Still processing..."
  sleep 5
done
```

## Command Reference

### Authentication

```bash
# Login
tracelab auth login --username <user> --password <pass>

# Check status
tracelab auth status

# Logout
tracelab auth logout

# Refresh token
tracelab auth refresh
```

### Projects

```bash
# List projects (supports paging & search)
tracelab projects list --page 1 --page-size 20
tracelab projects list --search "Discovery"
tracelab projects list --json

# Get project
tracelab projects get <project-id>

# Create project
tracelab projects create --name "Project Name" --description "..."

# Update project
tracelab projects update <project-id> --name "New Name"

# Delete project
tracelab projects delete <project-id> --confirm
```

### Documents

```bash
# Upload document
tracelab documents upload <project-id> <file-path>
tracelab documents upload <project-id> <file-path> --process --wait

# List documents (project filter optional)
tracelab documents list --project-id <project-id>
tracelab documents list --status processed --page 2 --page-size 25

# Get document
tracelab documents get <document-id>

# Process document
tracelab documents process <document-id> --wait

# Check status
tracelab documents status <document-id>

# Delete document
tracelab documents delete <document-id> --confirm
```

### Search

```bash
# Semantic search
tracelab search semantic <project-id> "query text" --top-k 10

# RAG query
tracelab rag query <project-id> "question?" --model gpt-4o --top-k 5
```

### Missions

```bash
# List missions
tracelab missions list <project-id>
tracelab missions list <project-id> --status draft

# Get mission
tracelab missions get <mission-id>

# Create mission
tracelab missions create <project-id> --title "Mission Title"
tracelab missions create <project-id> --title "..." --yaml mission.yaml

# Import from YAML
tracelab missions import <project-id> mission.yaml --promote

# Add evidence
tracelab missions add-evidence <mission-id> <chunk-id> --note "Supporting data"

# Validate mission
tracelab missions validate <mission-id>

# Export report
tracelab missions export <mission-id> --format md --output report.md
tracelab missions export <mission-id> --format pdf --output report.pdf

# Delete mission
tracelab missions delete <mission-id> --confirm
```

### Configuration

```bash
# Show config
tracelab config show

# Set value
tracelab config set api.base_url https://api.tracelab.dev
tracelab config set defaults.project_id proj-abc123

# Get value
tracelab config get api.base_url

# Reset config
tracelab config reset --confirm
```

### Utilities

```bash
# Version
tracelab version

# Health check
tracelab health
tracelab health --full

# Help
tracelab --help
tracelab <command> --help
```

## Global Flags

All commands support:

- `--json` - JSON output mode
- `--quiet` - Suppress non-essential output
- `--verbose` - Enable debug logging
- `--api-url <url>` - Override API URL
- `--token <token>` - Override stored token
- `--no-color` - Disable colors

Example:
```bash
tracelab projects list --json --api-url http://staging.api.com --page-size 50
```

## JSON Output Format

Success response:
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2025-11-10T12:00:00Z"
  }
}
```

Error response:
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Error message",
    "details": { ... }
  }
}
```

## Configuration

Config file location: `~/.tracelab/config.json`

Default configuration:
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

## Token Storage

Tokens stored at: `~/.tracelab/token` (chmod 600)

Token format:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_at": 1731240000.0
}
```

## Exit Codes

- `0` - Success
- `1` - General error
- `2` - Invalid arguments
- `3` - Authentication error
- `4` - Resource not found
- `5` - Permission denied
- `130` - Interrupted by user (Ctrl+C)

## Troubleshooting

### Authentication Issues

```bash
# Check auth status
tracelab auth status

# Re-login
tracelab auth logout
tracelab auth login --username your-username
```

### API Connection Issues

```bash
# Test API health
tracelab health --verbose

# Override API URL
tracelab --api-url http://localhost:8000 health
```

### Token Expired

```bash
# Refresh token
tracelab auth refresh

# Or re-login
tracelab auth login --username your-username
```

## Tips for Agents

1. **Always use `--json` flag** for parseable output
2. **Check exit codes** - non-zero means error
3. **Use `--confirm` flag** to skip prompts
4. **Store project IDs** in variables for reuse
5. **Poll status endpoints** for long operations
6. **Parse JSON with `jq`** for robust extraction

Example agent script:
```bash
#!/bin/bash
set -e  # Exit on error

# Login
tracelab auth login --username $USER --password $PASS --json > /dev/null

# Create project
PROJECT=$(tracelab projects create --name "Research" --json)
PROJECT_ID=$(echo "$PROJECT" | jq -r '.data.id')

# Upload docs
for file in *.pdf; do
  tracelab documents upload $PROJECT_ID "$file" --process --json
done

# Query
ANSWER=$(tracelab rag query $PROJECT_ID "Summarize findings" --json)
echo "$ANSWER" | jq -r '.data.answer'
```

## Support

For issues or questions:
- Documentation: `docs/`
- CLI Architecture: `docs/cli_architecture.md`
- API Docs: `http://localhost:8000/docs`
