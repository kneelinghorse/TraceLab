#!/usr/bin/env python3
"""Generate a doc_id -> mission_id/mission_uuid map for PEDR benchmarks."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.mission import Mission  # noqa: E402
from scripts import pedr_validation_benchmark as pvb  # noqa: E402
from scripts import rag_baseline_benchmark as rbb  # noqa: E402


SPRINT_RE = re.compile(r"sprint-(\\d+)", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z0-9]+")
KEYWORDS = {
    "pedr",
    "qdrant",
    "deepsearch",
    "graph",
    "ingestion",
    "schema",
    "auth",
    "cors",
    "telemetry",
    "quality",
    "benchmark",
    "deployment",
    "caching",
    "monitoring",
    "relationship",
    "mission",
    "protocol",
}


@dataclass(frozen=True)
class MissionRecord:
    mission_uuid: str
    mission_id: str
    title: str
    status: str


def _normalize(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower()))


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def _extract_sprint(source_path: str) -> Optional[str]:
    match = SPRINT_RE.search(source_path)
    return match.group(1) if match else None


def _keyword_overlap(doc_tokens: set[str], mission_tokens: set[str]) -> int:
    return len(KEYWORDS & doc_tokens & mission_tokens)


def score_mission(doc: Dict[str, str], mission: MissionRecord) -> float:
    doc_title = _normalize(doc["title"])
    mission_title = _normalize(mission.title)
    ratio = SequenceMatcher(None, doc_title, mission_title).ratio()

    doc_tokens = _tokens(doc["title"])
    mission_tokens = _tokens(mission.title)
    overlap = len(doc_tokens & mission_tokens)
    overlap_ratio = overlap / max(1, len(doc_tokens))

    score = 0.6 * ratio + 0.4 * overlap_ratio

    sprint = _extract_sprint(doc.get("source_path", ""))
    if sprint:
        mission_id_norm = mission.mission_id.lower()
        if f"b{sprint}" in mission_id_norm or f"sprint {sprint}" in mission.title.lower():
            score += 0.2

    score += 0.05 * _keyword_overlap(doc_tokens, mission_tokens)

    if mission.status == "completed":
        score += 0.05

    return score


def rank_missions(
    doc: Dict[str, str],
    missions: Iterable[MissionRecord],
) -> List[Tuple[MissionRecord, float]]:
    scored = [(mission, score_mission(doc, mission)) for mission in missions]
    return sorted(scored, key=lambda item: item[1], reverse=True)


def assign_missions(
    docs: List[Dict[str, str]],
    missions: List[MissionRecord],
    *,
    min_score: float,
) -> Tuple[Dict[str, Dict[str, str]], List[Tuple[str, float, str]]]:
    candidates = {
        doc["doc_id"]: rank_missions(doc, missions) for doc in docs
    }
    doc_order = sorted(
        docs,
        key=lambda doc: candidates[doc["doc_id"]][0][1] if candidates[doc["doc_id"]] else 0,
        reverse=True,
    )

    mapping: Dict[str, Dict[str, str]] = {}
    used = set()
    low_confidence: List[Tuple[str, float, str]] = []

    for doc in doc_order:
        doc_id = doc["doc_id"]
        ranked = candidates[doc_id]
        if not ranked:
            raise ValueError(f"No mission candidates for {doc_id}")

        chosen: Optional[Tuple[MissionRecord, float]] = None
        for mission, score in ranked:
            if mission.mission_id not in used:
                chosen = (mission, score)
                used.add(mission.mission_id)
                break
        if chosen is None:
            chosen = ranked[0]

        mission, score = chosen
        mapping[doc_id] = {
            "mission_id": mission.mission_id,
            "mission_uuid": mission.mission_uuid,
        }
        if score < min_score:
            low_confidence.append((doc_id, score, mission.mission_id))

    return mapping, low_confidence


def load_missions() -> List[MissionRecord]:
    session = SessionLocal()
    try:
        rows = session.query(
            Mission.id,
            Mission.mission_id,
            Mission.title,
            Mission.status,
        ).all()
        return [
            MissionRecord(
                mission_uuid=str(row.id),
                mission_id=row.mission_id,
                title=row.title,
                status=row.status or "draft",
            )
            for row in rows
        ]
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a doc_id -> mission map for PEDR benchmark metadata."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=pvb.DEFAULT_MISSION_MAP_PATH,
        help="Output path for mission_map.json.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.25,
        help="Warn if the best match score falls below this threshold.",
    )

    args = parser.parse_args()

    docs = rbb.SOURCE_DOCS
    missions = load_missions()
    mapping, low_confidence = assign_missions(docs, missions, min_score=args.min_score)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(mapping, indent=2), encoding="utf-8")

    print(f"Wrote mission map: {args.output}")
    print(f"Mapped docs: {len(mapping)}")
    print(f"Available missions: {len(missions)}")
    if low_confidence:
        print("Low-confidence matches:")
        for doc_id, score, mission_id in sorted(low_confidence, key=lambda item: item[1]):
            print(f"  {doc_id}: {score:.2f} -> {mission_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
