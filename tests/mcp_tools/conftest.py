"""Conftest for MCP tests - excludes database autouse fixture.

MCP tool unit tests don't require database access and should not
trigger the autouse database reset fixture from the main conftest.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Setup path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set test environment
os.environ.setdefault("ENVIRONMENT", "test")
