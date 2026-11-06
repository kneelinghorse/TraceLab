#!/usr/bin/env bash
# Resets rbook/ to a clean starter state by clearing runtime data
# while preserving structure, templates, and documentation.
# Run from anywhere: ./rbook/scripts/reset_starter.sh

set -euo pipefail

# Find rbook/ directory (script is in rbook/scripts/)
CMOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🧹 Resetting CMOS starter to clean state..."
echo "   Working in: ${CMOS_DIR}"

# Backup current state (optional)
BACKUP_DIR="${CMOS_DIR}/dist/backup-$(date -u +"%Y%m%dT%H%M%SZ")"
mkdir -p "${BACKUP_DIR}"
echo "📦 Creating backup at: ${BACKUP_DIR}"

# Backup key runtime files
[ -f "${CMOS_DIR}/db/rbook.sqlite" ] && cp "${CMOS_DIR}/db/rbook.sqlite" "${BACKUP_DIR}/"
[ -f "${CMOS_DIR}/SESSIONS.jsonl" ] && cp "${CMOS_DIR}/SESSIONS.jsonl" "${BACKUP_DIR}/"
[ -f "${CMOS_DIR}/PROJECT_CONTEXT.json" ] && cp "${CMOS_DIR}/PROJECT_CONTEXT.json" "${BACKUP_DIR}/"
[ -f "${CMOS_DIR}/context/MASTER_CONTEXT.json" ] && cp "${CMOS_DIR}/context/MASTER_CONTEXT.json" "${BACKUP_DIR}/"

echo "✨ Clearing runtime data..."

# Clear database
if [ -f "${CMOS_DIR}/db/rbook.sqlite" ]; then
    rm "${CMOS_DIR}/db/rbook.sqlite"
    echo "   ✓ Removed db/rbook.sqlite"
fi

# Clear sessions
if [ -f "${CMOS_DIR}/SESSIONS.jsonl" ]; then
    rm "${CMOS_DIR}/SESSIONS.jsonl"
    echo "   ✓ Removed SESSIONS.jsonl"
fi

# Reset PROJECT_CONTEXT.json to empty state
cat > "${CMOS_DIR}/PROJECT_CONTEXT.json" << 'EOF'
{
  "working_memory": {
    "active_mission": null,
    "session_count": 0,
    "last_completed_mission": null,
    "session_history": []
  },
  "context_health": {
    "agents_md_loaded": false,
    "last_updated": null
  },
  "technical_context": {
    "dependencies": [
      "Python 3.11+",
      "Node.js 20+ (for optional tooling and tests)"
    ],
    "tooling": {
      "seed_database": "python rbook/scripts/seed_sqlite.py --data-root <path-to-planning-repo>",
      "validate_health": "./rbook/cli.py validate health",
      "mission_runtime": "./rbook/cli.py mission --help"
    },
    "reference_docs": [
      "foundational-docs/roadmap_template.md",
      "foundational-docs/tech_arch_template.md"
    ]
  }
}
EOF
echo "   ✓ Reset PROJECT_CONTEXT.json"

# Reset MASTER_CONTEXT.json to empty state
cat > "${CMOS_DIR}/context/MASTER_CONTEXT.json" << 'EOF'
{
  "project_identity": {},
  "technical_foundation": {},
  "decisions_made": [],
  "constraints": [],
  "quality_standards": {}
}
EOF
echo "   ✓ Reset context/MASTER_CONTEXT.json"

# Clear backlog (keep structure)
cat > "${CMOS_DIR}/missions/backlog.yaml" << 'EOF'
---
name: Planning.SprintPlan.v1
version: 0.0.0
displayName: CMOS Starter Backlog
description: Empty backlog template for new CMOS projects
author: CMOS
schema: ./schemas/SprintPlan.v1.json
---
domainFields:
  type: Planning.SprintPlan.v1
  sprints: []
  missionDependencies: []
  promptMapping:
    prompts: []
EOF
echo "   ✓ Reset missions/backlog.yaml"

# Clear telemetry events (preserve structure)
if [ -d "${CMOS_DIR}/telemetry/events" ]; then
    find "${CMOS_DIR}/telemetry/events" -name "*.jsonl" -type f -delete 2>/dev/null || true
    find "${CMOS_DIR}/telemetry/events" -name "*.json" -type f ! -name "*schema*" -delete 2>/dev/null || true
    echo "   ✓ Cleared telemetry/events/"
fi

# Clear runtime boomerang state
if [ -d "${CMOS_DIR}/runtime/boomerang" ]; then
    find "${CMOS_DIR}/runtime/boomerang" -type f -delete 2>/dev/null || true
    echo "   ✓ Cleared runtime/boomerang/"
fi

# Remove inventory file if exists
if [ -f "${CMOS_DIR}/PHASE1_INVENTORY.md" ]; then
    rm "${CMOS_DIR}/PHASE1_INVENTORY.md"
    echo "   ✓ Removed PHASE1_INVENTORY.md"
fi

echo ""
echo "✅ Reset complete! CMOS starter is now in clean state."
echo "   Backup saved to: ${BACKUP_DIR}"
echo ""
echo "Next steps:"
echo "  1. Review reset state"
echo "  2. Run: python rbook/scripts/seed_sqlite.py (to create empty DB)"
echo "  3. Run: ./rbook/scripts/package_starter.sh (to create distribution)"
echo ""
