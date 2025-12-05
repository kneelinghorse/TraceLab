#!/usr/bin/env python3
"""Example CLI for DeepSearch pre-flight queries.

This script demonstrates how DeepSearch agents can query TraceLab
before launching new research missions, enabling reuse of existing
high-quality research.

Usage:
    # Check if research exists before starting new mission
    python scripts/preflight_example.py "passwordless authentication patterns"

    # With custom thresholds
    python scripts/preflight_example.py "WebAuthn implementation" --min-gates 3

    # JSON output for programmatic use
    python scripts/preflight_example.py "SSO integration patterns" --json

Environment:
    TRACELAB_BASE_URL: API base URL (default: http://localhost:8000)
    TRACELAB_TOKEN: JWT access token for authentication

Example workflow:
    1. DeepSearch receives research objective
    2. Call preflight endpoint to check existing research
    3. If action == "reuse": Use existing mission data
    4. If action == "review": Check matches before proceeding
    5. If action == "proceed": Launch new research mission
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


@dataclass
class PreflightConfig:
    """Configuration for pre-flight queries."""
    base_url: str
    token: str
    min_quality_gates: int = 4
    status: List[str] = None
    top_k: int = 5
    similarity_threshold: float = 0.70

    def __post_init__(self):
        if self.status is None:
            self.status = ["complete"]


def preflight_query(
    query: str,
    config: PreflightConfig,
    agent_id: str = "deepsearch-cli",
) -> Dict[str, Any]:
    """Execute pre-flight query against TraceLab API.

    Args:
        query: Research objective or topic to check
        config: API configuration
        agent_id: Identifier for the calling agent

    Returns:
        Pre-flight recommendation response

    Raises:
        requests.HTTPError: If API request fails
    """
    url = f"{config.base_url}/api/v1/pedr/preflight"

    headers = {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
        "X-Agent-ID": agent_id,
    }

    payload = {
        "query": query,
        "min_quality_gates": config.min_quality_gates,
        "status": config.status,
        "top_k": config.top_k,
        "similarity_threshold": config.similarity_threshold,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    return response.json()


def format_match(match: Dict[str, Any], index: int) -> str:
    """Format a single match for display."""
    lines = [
        f"\n  [{index + 1}] {match.get('title', 'Untitled')}",
        f"      Mission ID: {match.get('mission_id', 'N/A')}",
        f"      Similarity: {match.get('similarity_score', 0):.0%}",
        f"      Quality: {match.get('quality_gates_passed', 0)}/{match.get('quality_gates_total', 5)} gates",
        f"      Status: {match.get('status', 'unknown')}",
    ]

    objective = match.get("objective", "")
    if objective:
        lines.append(f"      Objective: {objective[:80]}{'...' if len(objective) > 80 else ''}")

    insights = match.get("key_insights", [])
    if insights:
        lines.append("      Key Insights:")
        for insight in insights[:3]:
            text = insight.get("text", "") if isinstance(insight, dict) else str(insight)
            lines.append(f"        - {text[:60]}{'...' if len(text) > 60 else ''}")

    return "\n".join(lines)


def format_recommendation(result: Dict[str, Any]) -> str:
    """Format the full recommendation for display."""
    action = result.get("action", "unknown")
    action_symbols = {"reuse": "✓", "review": "?", "proceed": "→"}
    symbol = action_symbols.get(action, "•")

    lines = [
        "",
        f"{'=' * 60}",
        f"Pre-Flight Query Result",
        f"{'=' * 60}",
        "",
        f"  Query: {result.get('query', 'N/A')}",
        "",
        f"  {symbol} Action: {action.upper()}",
        f"  Summary: {result.get('summary', 'N/A')}",
        "",
        f"  Matches: {result.get('match_count', 0)}",
    ]

    if result.get("top_score"):
        lines.append(f"  Top Score: {result['top_score']:.0%}")

    lines.append(f"  Latency: {result.get('latency_ms', 0):.1f}ms")

    matches = result.get("matches", [])
    if matches:
        lines.append("\n  Matching Missions:")
        for i, match in enumerate(matches):
            lines.append(format_match(match, i))

    lines.extend([
        "",
        f"{'=' * 60}",
        "",
    ])

    return "\n".join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Check TraceLab for existing research before launching new missions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "passwordless authentication patterns"
  %(prog)s "WebAuthn security" --min-gates 3 --json
  %(prog)s "OAuth2 integration" --status complete review

Environment Variables:
  TRACELAB_BASE_URL  API base URL (default: http://localhost:8000)
  TRACELAB_TOKEN     JWT access token for authentication
        """,
    )

    parser.add_argument(
        "query",
        help="Research objective or topic to check",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TRACELAB_BASE_URL", "http://localhost:8000"),
        help="TraceLab API base URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("TRACELAB_TOKEN", ""),
        help="JWT access token (or set TRACELAB_TOKEN env var)",
    )
    parser.add_argument(
        "--min-gates",
        type=int,
        default=4,
        choices=[0, 1, 2, 3, 4, 5],
        help="Minimum passing quality gates (default: 4)",
    )
    parser.add_argument(
        "--status",
        nargs="+",
        default=["complete"],
        help="Allowed mission statuses (default: complete)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum matches to return (default: 5)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.70,
        help="Minimum similarity threshold (default: 0.70)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response",
    )
    parser.add_argument(
        "--agent-id",
        default="deepsearch-cli",
        help="Agent identifier for telemetry",
    )

    args = parser.parse_args()

    if not args.token:
        print("Error: No authentication token provided.")
        print("Set TRACELAB_TOKEN environment variable or use --token flag.")
        sys.exit(1)

    config = PreflightConfig(
        base_url=args.base_url.rstrip("/"),
        token=args.token,
        min_quality_gates=args.min_gates,
        status=args.status,
        top_k=args.top_k,
        similarity_threshold=args.threshold,
    )

    try:
        result = preflight_query(args.query, config, agent_id=args.agent_id)
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {config.base_url}")
        print("Make sure TraceLab is running and accessible.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("Error: Authentication failed. Check your access token.")
        else:
            print(f"Error: API request failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_recommendation(result))

        # Exit with code based on action
        action = result.get("action", "proceed")
        if action == "reuse":
            sys.exit(0)  # Success - use existing research
        elif action == "review":
            sys.exit(2)  # Review needed
        else:
            sys.exit(3)  # Proceed with new research


if __name__ == "__main__":
    main()
