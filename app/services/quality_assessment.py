"""Rule-based quality assessment for tiered LLM routing."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, Iterable, List, Sequence


_CITATION_PATTERN = re.compile(
    r"\[Document:\s*[^,\]]+,\s*Chunk:\s*[^]]+\]", re.IGNORECASE
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _normalize_patterns(patterns: Sequence[str]) -> List[re.Pattern[str]]:
    return [re.compile(pat, re.IGNORECASE) for pat in patterns]


@dataclass
class QualityAssessmentConfig:
    """Configuration for the rule-based quality heuristics."""

    escalation_threshold: float = 0.85
    linguistic_weight: float = 0.35
    integrity_weight: float = 0.35
    provenance_weight: float = 0.30
    hedging_patterns: Sequence[str] = field(
        default_factory=lambda: [
            r"\bmaybe\b",
            r"\bperhaps\b",
            r"\bpossibly\b",
            r"\bcould\b",
            r"\bmight\b",
            r"\bnot sure\b",
            r"\buncertain\b",
            r"\bit seems\b",
            r"\bi think\b",
        ]
    )
    refusal_patterns: Sequence[str] = field(
        default_factory=lambda: [
            r"\bi (?:cannot|can't) (?:help|comply|answer)",
            r"\bi'm sorry\b",
            r"\bas an ai (?:language )?model\b",
            r"\bi do not have access\b",
            r"\bi (?:do )?not have enough information\b",
        ]
    )
    placeholder_tokens: Sequence[str] = field(
        default_factory=lambda: [
            r"\bto be determined\b",
            r"\btbd\b",
            r"\bfill in\b",
            r"\bplaceholder\b",
            r"\blorem ipsum\b",
        ]
    )
    min_answer_chars: int = 40
    min_sentences_with_citations: float = 0.5


@dataclass
class QualityAssessmentResult:
    """Outcome of a single quality assessment run."""

    composite_score: float
    threshold: float
    pillar_scores: Dict[str, float]
    hard_failures: List[str]
    escalate: bool
    reasons: List[str] = field(default_factory=list)


class QualityAssessor:
    """Evaluate generated answers using deterministic heuristics."""

    def __init__(self, config: QualityAssessmentConfig | None = None) -> None:
        self.config = config or QualityAssessmentConfig()
        self._hedging_patterns = _normalize_patterns(self.config.hedging_patterns)
        self._refusal_patterns = _normalize_patterns(self.config.refusal_patterns)
        self._placeholder_patterns = _normalize_patterns(self.config.placeholder_tokens)

    def assess(
        self,
        *,
        query: str,
        answer: str,
        citations: Iterable[Dict[str, object]],
        context_chunks: Iterable[Dict[str, object]] | None = None,
    ) -> QualityAssessmentResult:
        """Run the quality heuristics and return an assessment result."""
        del query  # currently unused but retained for future heuristics
        citations_list = list(citations)
        hard_failures = self._detect_hard_failures(answer)

        pillar_scores = {
            "linguistic_uncertainty": self._score_linguistic_uncertainty(answer),
            "answer_integrity": self._score_answer_integrity(answer, context_chunks),
            "source_provenance": self._score_source_provenance(answer, citations_list),
        }

        composite_score = self._composite_score(pillar_scores)
        reasons: List[str] = []

        if hard_failures:
            reasons.extend(f"hard_fail:{failure}" for failure in hard_failures)

        if composite_score < self.config.escalation_threshold:
            reasons.append(
                f"score_below_threshold:{composite_score:.2f}<{self.config.escalation_threshold:.2f}"
            )

        escalate = bool(hard_failures) or composite_score < self.config.escalation_threshold

        return QualityAssessmentResult(
            composite_score=composite_score,
            threshold=self.config.escalation_threshold,
            pillar_scores=pillar_scores,
            hard_failures=hard_failures,
            escalate=escalate,
            reasons=reasons,
        )

    def _detect_hard_failures(self, answer: str) -> List[str]:
        failures: List[str] = []
        if not answer.strip():
            failures.append("empty_answer")
            return failures

        for pattern in self._refusal_patterns:
            if pattern.search(answer):
                failures.append("refusal_detected")
                break

        for pattern in self._placeholder_patterns:
            if pattern.search(answer):
                failures.append("placeholder_detected")
                break

        if "citation" in answer.lower() and "[document:" not in answer.lower():
            failures.append("citation_reference_without_links")

        return failures

    def _score_linguistic_uncertainty(self, answer: str) -> float:
        score = 1.0
        hedges = 0
        for pattern in self._hedging_patterns:
            matches = pattern.findall(answer)
            if matches:
                hedges += len(matches)
        if hedges:
            score -= min(0.1 * hedges, 0.5)
        return max(0.0, round(score, 3))

    def _score_answer_integrity(
        self,
        answer: str,
        context_chunks: Iterable[Dict[str, object]] | None,
    ) -> float:
        content = answer.strip()
        if len(content) < self.config.min_answer_chars:
            return 0.6

        lowered = content.lower()
        if any(token in lowered for token in ("insufficient information", "cannot determine", "not provided")):
            return 0.55

        if context_chunks:
            unique_docs = {chunk.get("document_id") for chunk in context_chunks if chunk.get("document_id")}
            if unique_docs and len(unique_docs) < 1:
                return 0.7
        return 0.95

    def _score_source_provenance(self, answer: str, citations: Sequence[Dict[str, object]]) -> float:
        if not citations:
            return 0.4

        sentences = [sent for sent in _SENTENCE_SPLIT.split(answer.strip()) if sent]
        if not sentences:
            return 0.4

        sentences_with_citations = sum(1 for sentence in sentences if _CITATION_PATTERN.search(sentence))
        coverage = sentences_with_citations / max(len(sentences), 1)
        if coverage >= self.config.min_sentences_with_citations:
            return 0.95
        if coverage >= 0.3:
            return 0.75
        return 0.55

    def _composite_score(self, pillar_scores: Dict[str, float]) -> float:
        score = (
            pillar_scores["linguistic_uncertainty"] * self.config.linguistic_weight
            + pillar_scores["answer_integrity"] * self.config.integrity_weight
            + pillar_scores["source_provenance"] * self.config.provenance_weight
        )
        return round(score, 3)
