"""Advanced accuracy tests for the Presidio evaluator."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.presidio_evaluator import PresidioEvaluator


class _StubAnalyzer:
    """Minimal Presidio analyzer stub with queued responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def analyze(self, text: str, language: str = "en"):
        del text, language
        if self.calls >= len(self._responses):
            return []
        result = self._responses[self.calls]
        self.calls += 1
        return result


def _span_for(text: str, value: str, entity: str) -> SimpleNamespace:
    start = text.index(value)
    return SimpleNamespace(entity_type=entity, start=start, end=start + len(value))


def _build_evaluator(monkeypatch, responses, samples) -> PresidioEvaluator:
    analyzer = _StubAnalyzer(responses)
    evaluator = PresidioEvaluator.__new__(PresidioEvaluator)
    evaluator.analyzer = analyzer  # type: ignore[attr-defined]
    monkeypatch.setattr(evaluator, "load_corpus_samples", lambda: list(samples))
    return evaluator


def test_priority_evaluation_reports_precision_and_recall(monkeypatch):
    """Precision/recall metrics should reflect true/false positives and negatives."""
    sample_one_text = "Reach PID-2024-1111 at +1 (415) 555-0100 for PROJ-UX."  # noqa: S105 - synthetic data
    sample_two_text = (
        "Participant PARTICIPANT-ALPHA-2222 left a voicemail at 303-777-2222 "
        "while referencing PID-CONTROL-0000."
    )

    samples = [
        SimpleNamespace(
            full_text=sample_one_text,
            metadata={
                "entities": {
                    "PARTICIPANT_ID": ["PID-2024-1111"],
                    "PHONE_NUMBER": ["+1 (415) 555-0100"],
                }
            },
        ),
        SimpleNamespace(
            full_text=sample_two_text,
            metadata={
                "entities": {
                    "PARTICIPANT_ID": ["PARTICIPANT-ALPHA-2222"],
                    "PHONE_NUMBER": ["303-777-2222"],
                }
            },
        ),
    ]

    responses = [
        [
            _span_for(sample_one_text, "PID-2024-1111", "PARTICIPANT_ID"),
            _span_for(sample_one_text, "+1 (415) 555-0100", "PHONE_NUMBER"),
        ],
        [
            _span_for(sample_two_text, "PARTICIPANT-ALPHA-2222", "PARTICIPANT_ID"),
            _span_for(sample_two_text, "PID-CONTROL-0000", "PARTICIPANT_ID"),
        ],
    ]

    evaluator = _build_evaluator(monkeypatch, responses, samples)
    report = evaluator.evaluate_priority_entities(["PARTICIPANT_ID", "PHONE_NUMBER"])

    assert report["total_samples"] == 2
    assert set(report["priority_entities"]) == {"PARTICIPANT_ID", "PHONE_NUMBER"}
    overall = report["metrics"]["overall"]
    assert overall["true_positives"] == 3  # two participant IDs + one phone number
    assert overall["false_negatives"] == 1  # missing phone detection in sample two
    assert overall["false_positives"] == 1  # extra participant ID in sample two

    participant_metrics = report["per_entity"]["PARTICIPANT_ID"]
    assert participant_metrics["precision"] == pytest.approx(2 / 3)
    assert participant_metrics["recall"] == pytest.approx(1.0)

    phone_metrics = report["per_entity"]["PHONE_NUMBER"]
    assert phone_metrics["precision"] == pytest.approx(1.0)
    assert phone_metrics["recall"] == pytest.approx(0.5)


def test_priority_evaluation_handles_mixed_metadata_structures(monkeypatch):
    """Entity metadata stored as dicts or whitespace-heavy values should normalize cleanly."""
    text = "Call (415) 555-0000 for PARTICIPANT-ALPHA-9000 support."  # noqa: S105 - synthetic data
    samples = [
        SimpleNamespace(
            full_text=text,
            metadata={
                "entities": {
                    "PARTICIPANT_ID": {"primary": " participant-alpha-9000 "},
                    "PHONE_NUMBER": [" (415) 555-0000 "],
                }
            },
        )
    ]

    responses = [
        [
            _span_for(text, "PARTICIPANT-ALPHA-9000", "PARTICIPANT_ID"),
            _span_for(text, "(415) 555-0000", "PHONE_NUMBER"),
        ]
    ]

    evaluator = _build_evaluator(monkeypatch, responses, samples)
    report = evaluator.evaluate_priority_entities(["PARTICIPANT_ID", "PHONE_NUMBER"])

    overall = report["metrics"]["overall"]
    assert overall["true_positives"] == 2
    assert overall["false_negatives"] == 0
    assert overall["false_positives"] == 0
