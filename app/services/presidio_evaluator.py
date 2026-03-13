"""
Simplified evaluator stub maintained for backwards compatibility.

The original implementation depended on Presidio's analyzer/evaluator stack. This
module keeps the public API surface used by internal tests while operating solely
on in-memory samples and analyzer stubs provided by the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


class PresidioEvaluator:
    """Lightweight evaluator that compares analyzer spans against sample metadata."""

    def __init__(self, corpus_dir: str | None = None) -> None:
        self.corpus_dir = corpus_dir
        self.analyzer = None  # Tests inject stub analyzers directly.

    # -- Legacy compatibility -------------------------------------------------
    def load_corpus_samples(self) -> list[Any]:
        """Return corpus samples. Overridden/mocked in tests."""
        return []

    # -- Evaluation -----------------------------------------------------------
    def evaluate_priority_entities(
        self, priority_entities: Sequence[str]
    ) -> dict[str, Any]:
        if self.analyzer is None:
            raise RuntimeError("Analyzer not configured for PresidioEvaluator.")

        samples = self.load_corpus_samples()
        priority = list(priority_entities)
        per_entity = {
            entity: {
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
            }
            for entity in priority
        }
        overall = {
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }

        for sample in samples:
            expected = self._expected_entities(sample, priority)
            predictions = self._predicted_entities(sample, priority)
            for entity in priority:
                exp_set = expected[entity]
                pred_set = predictions[entity]
                tp = len(exp_set & pred_set)
                fp = len(pred_set - exp_set)
                fn = len(exp_set - pred_set)
                per_entity[entity]["true_positives"] += tp
                per_entity[entity]["false_positives"] += fp
                per_entity[entity]["false_negatives"] += fn
                overall["true_positives"] += tp
                overall["false_positives"] += fp
                overall["false_negatives"] += fn

        for entity in priority:
            stats = per_entity[entity]
            stats["precision"] = self._precision(
                stats["true_positives"], stats["false_positives"]
            )
            stats["recall"] = self._recall(
                stats["true_positives"], stats["false_negatives"]
            )
            stats["f1"] = self._f1(stats["precision"], stats["recall"])

        overall["precision"] = self._precision(
            overall["true_positives"], overall["false_positives"]
        )
        overall["recall"] = self._recall(
            overall["true_positives"], overall["false_negatives"]
        )
        overall["f1"] = self._f1(overall["precision"], overall["recall"])

        return {
            "total_samples": len(samples),
            "priority_entities": priority,
            "metrics": {"overall": overall},
            "per_entity": per_entity,
        }

    # -- Deprecated surface ---------------------------------------------------
    def run_regression_evaluation(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        """Former Presidio hook retained for CLI compatibility."""
        raise RuntimeError(
            "Presidio integration has been removed; regression evaluation is no longer available."
        )

    # -- Helpers --------------------------------------------------------------
    def _expected_entities(
        self, sample: Any, priority: Sequence[str]
    ) -> dict[str, set[str]]:
        metadata = getattr(sample, "metadata", {}) or {}
        entities = metadata.get("entities", {})
        expected: dict[str, set[str]] = {entity: set() for entity in priority}
        for entity, values in entities.items():
            if entity not in expected:
                continue
            expected[entity].update(self._normalize_metadata_values(values))
        return expected

    def _predicted_entities(
        self, sample: Any, priority: Sequence[str]
    ) -> dict[str, set[str]]:
        predictions: dict[str, set[str]] = {entity: set() for entity in priority}
        text = getattr(sample, "full_text", "")
        spans = self.analyzer.analyze(text, language="en")
        for span in spans:
            entity_type = getattr(span, "entity_type", None)
            if entity_type not in predictions:
                continue
            value = text[getattr(span, "start", 0) : getattr(span, "end", 0)]
            normalized = self._normalize_text_value(value)
            if normalized:
                predictions[entity_type].add(normalized)
        return predictions

    @staticmethod
    def _normalize_metadata_values(values: Any) -> set[str]:
        normalized: set[str] = set()
        if values is None:
            return normalized
        if isinstance(values, dict):
            iterable: Iterable[Any] = values.values()
        elif isinstance(values, (list, tuple, set)):
            iterable = values
        else:
            iterable = [values]

        for entry in iterable:
            if isinstance(entry, dict):
                normalized.update(PresidioEvaluator._normalize_metadata_values(entry))
                continue
            token = str(entry).strip()
            if token:
                normalized.add(token.upper())
        return normalized

    @staticmethod
    def _normalize_text_value(value: str) -> str:
        token = (value or "").strip()
        return token.upper()

    @staticmethod
    def _precision(tp: int, fp: int) -> float:
        denominator = tp + fp
        if denominator == 0:
            return 0.0
        return tp / denominator

    @staticmethod
    def _recall(tp: int, fn: int) -> float:
        denominator = tp + fn
        if denominator == 0:
            return 0.0
        return tp / denominator

    @staticmethod
    def _f1(precision: float, recall: float) -> float:
        denominator = precision + recall
        if denominator == 0:
            return 0.0
        return 2 * (precision * recall) / denominator
