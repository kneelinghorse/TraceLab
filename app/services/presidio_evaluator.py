"""
Presidio Evaluation Harness

Loads the synthetic corpus annotations produced by the corpus generator and
evaluates Presidio using presidio-research utilities, reporting precision/recall
metrics per entity type.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document

try:
    from pdfminer.high_level import extract_text as extract_pdf_text
except ImportError:  # pragma: no cover - handled gracefully when optional dependency missing
    extract_pdf_text = None

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_evaluator import InputSample
from presidio_evaluator.data_objects import Span
from presidio_evaluator.evaluation.span_evaluator import SpanEvaluator
from presidio_evaluator.models.presidio_analyzer_wrapper import PresidioAnalyzerWrapper


class PresidioEvaluator:
    """Evaluates Presidio PII detection on the synthetic corpus."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".docx", ".pdf"}

    def __init__(
        self,
        corpus_dir: str = "data/corpus",
        spacy_model: str = "en_core_web_sm",
        analyzer_engine: Optional[AnalyzerEngine] = None,
    ) -> None:
        """
        Args:
            corpus_dir: Directory containing corpus documents and annotations.
            spacy_model: spaCy model used by the Presidio analyzer.
            analyzer_engine: Optional preconfigured AnalyzerEngine to reuse.
        """
        self.corpus_dir = Path(corpus_dir).resolve()
        self.annotations_dir = self.corpus_dir / "annotations"
        self.spacy_model = spacy_model

        if analyzer_engine is not None:
            self.analyzer = analyzer_engine
        else:
            # Ensure the requested spaCy model is available for Presidio.
            self._ensure_spacy_model(spacy_model)

            nlp_configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": spacy_model}],
            }
            provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
            nlp_engine = provider.create_engine()

            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)

        self.wrapper = PresidioAnalyzerWrapper(analyzer_engine=self.analyzer, language="en")
        self.evaluator = SpanEvaluator(model=self.wrapper)

    # ------------------------------------------------------------------ priority evaluation helpers

    PRIORITY_NORMALIZATION_RULES: Dict[str, Any] = {
        "EMAIL_ADDRESS": lambda value: value.strip().lower(),
        "PHONE_NUMBER": lambda value: re.sub(r"\D", "", value),
        "PARTICIPANT_ID": lambda value: value.replace(" ", "").upper(),
        "PROJECT_ID": lambda value: value.replace(" ", "").upper(),
        "PERSON": lambda value: " ".join(value.strip().split()),
    }

    def evaluate_priority_entities(
        self,
        target_entities: List[str],
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Evaluate recall/precision for a targeted set of entities using corpus metadata.

        The synthetic corpus metadata includes canonical values for priority entities
        (e.g., participant/contact fields). This evaluation focuses on those high-value
        fields to measure tuned recognizer performance.
        """
        samples = self.load_corpus_samples()
        priority = set(target_entities)

        metrics: Dict[str, Dict[str, int]] = {
            entity: {"true_positives": 0, "false_positives": 0, "false_negatives": 0}
            for entity in priority
        }
        sample_coverage = 0

        for sample in samples:
            metadata = sample.metadata or {}
            entities_meta = metadata.get("entities") or {}

            expected_map: Dict[str, set] = {}
            for entity in priority:
                if entity not in entities_meta:
                    continue
                expected_values = self._normalize_expected_values(entity, entities_meta[entity])
                if expected_values:
                    expected_map[entity] = expected_values

            if not expected_map:
                continue

            sample_coverage += 1
            analysis_results = self.analyzer.analyze(text=sample.full_text, language=language)

            detected: Dict[str, set] = {entity: set() for entity in priority}
            for result in analysis_results:
                entity_type = result.entity_type
                if entity_type not in priority:
                    continue
                span_text = sample.full_text[result.start : result.end]
                normalized = self._normalize_detected_value(entity_type, span_text)
                if normalized:
                    detected[entity_type].add(normalized)

            for entity in priority:
                expected = expected_map.get(entity)
                if not expected:
                    continue
                found = detected.get(entity, set())
                matches = expected & found

                metrics[entity]["true_positives"] += len(matches)
                metrics[entity]["false_negatives"] += len(expected - matches)
                metrics[entity]["false_positives"] += len(found - matches)

        per_entity_metrics: Dict[str, Dict[str, Any]] = {}
        overall_tp = overall_fp = overall_fn = 0

        for entity in priority:
            counts = metrics[entity]
            tp = counts["true_positives"]
            fp = counts["false_positives"]
            fn = counts["false_negatives"]

            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = (
                (2 * precision * recall) / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )

            per_entity_metrics[entity] = {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": tp + fn,
                "predicted": tp + fp,
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
            }

            overall_tp += tp
            overall_fp += fp
            overall_fn += fn

        overall_precision = overall_tp / (overall_tp + overall_fp) if (overall_tp + overall_fp) else 0.0
        overall_recall = overall_tp / (overall_tp + overall_fn) if (overall_tp + overall_fn) else 0.0
        overall_f1 = (
            (2 * overall_precision * overall_recall) / (overall_precision + overall_recall)
            if (overall_precision + overall_recall) > 0
            else 0.0
        )

        return {
            "total_samples": sample_coverage,
            "priority_entities": list(priority),
            "metrics": {
                "overall": {
                    "precision": overall_precision,
                    "recall": overall_recall,
                    "f1": overall_f1,
                    "true_positives": overall_tp,
                    "false_positives": overall_fp,
                    "false_negatives": overall_fn,
                    "annotated": overall_tp + overall_fn,
                    "predicted": overall_tp + overall_fp,
                }
            },
            "per_entity": per_entity_metrics,
        }

    def _normalize_detected_value(self, entity: str, value: str) -> Optional[str]:
        """Normalize detected text for comparison."""
        if not value:
            return None
        processor = self.PRIORITY_NORMALIZATION_RULES.get(entity)
        normalized = processor(value) if processor else value.strip()
        return normalized or None

    def _normalize_expected_values(self, entity: str, raw_value: Any) -> set:
        """Normalize metadata-defined expected entity values to a comparable set."""
        values: List[str]
        if raw_value is None:
            return set()
        if isinstance(raw_value, (list, tuple, set)):
            values = [str(item) for item in raw_value if item]
        elif isinstance(raw_value, dict):
            # Metadata may wrap values in dict (e.g., location). Use best-effort extraction.
            values = [str(val) for val in raw_value.values() if isinstance(val, str)]
        else:
            values = [str(raw_value)]

        normalized_set = set()
        for item in values:
            normalized = self._normalize_detected_value(entity, item)
            if normalized:
                normalized_set.add(normalized)
        return normalized_set

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _ensure_spacy_model(model_name: str) -> None:
        """Download the spaCy model if it is not already installed."""
        try:
            import spacy
            from spacy.util import is_package

            if not is_package(model_name):
                import spacy.cli

                print(f"Downloading spaCy model '{model_name}' for Presidio evaluator...")
                spacy.cli.download(model_name)
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"Warning: Could not ensure spaCy model '{model_name}': {exc}")

    def _resolve_document_path(self, path_str: Optional[str]) -> Optional[Path]:
        """Resolve a document path string to an existing Path, if possible."""
        if not path_str:
            return None

        candidate = Path(path_str)
        if candidate.exists():
            return candidate

        joined = (self.corpus_dir / candidate).resolve()
        if joined.exists():
            return joined

        return None

    def _infer_document_path(self, annotation_file: Path) -> Optional[Path]:
        """
        Infer the original document path from an annotation file name when metadata
        did not record it explicitly.
        """
        stem = annotation_file.stem.replace("_annotations", "")
        for candidate in self.corpus_dir.rglob(f"{stem}*"):
            suffix = candidate.suffix.lower()
            if suffix in self.SUPPORTED_EXTENSIONS and suffix != ".json":
                return candidate
        return None

    def _read_document_text(self, doc_file: Path) -> Optional[str]:
        """Extract textual content from a supported document type."""
        if not doc_file or not doc_file.exists():
            return None

        suffix = doc_file.suffix.lower()
        try:
            if suffix in {".txt", ".md", ".markdown", ".csv"}:
                return doc_file.read_text(encoding="utf-8")
            if suffix == ".docx":
                document = Document(str(doc_file))
                return "\n".join(paragraph.text for paragraph in document.paragraphs)
            if suffix == ".pdf":
                if extract_pdf_text is None:
                    print(f"Warning: pdfminer.six not installed; skipping PDF {doc_file}")
                    return None
                return extract_pdf_text(str(doc_file))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Warning: Unable to extract text from {doc_file}: {exc}")
            return None

        print(f"Warning: Unsupported file type for evaluation: {doc_file}")
        return None

    def _load_annotation_payload(
        self,
        annotation_file: Path,
    ) -> Optional[Tuple[str, List[Dict[str, Any]], Dict[str, Any]]]:
        """
        Load annotation JSON and resolve accompanying source text & metadata.

        Returns:
            Tuple of (source_text, annotations, metadata) or None if invalid.
        """
        try:
            with open(annotation_file, "r", encoding="utf-8") as handle:
                payload: Any = json.load(handle)
        except Exception as exc:
            print(f"Warning: Could not parse annotation file {annotation_file}: {exc}")
            return None

        annotations: List[Dict[str, Any]]
        document_path: Optional[Path] = None
        source_text: Optional[str] = None
        metadata: Dict[str, Any] = {}

        if isinstance(payload, list):
            annotations = payload
        else:
            annotations = payload.get("annotations", [])
            metadata = payload.get("metadata", {}) or {}
            document_path = self._resolve_document_path(
                payload.get("document_absolute") or payload.get("document_path")
            )
            source_text = payload.get("source_text")

        if not annotations:
            print(f"Warning: Annotation file contains no spans: {annotation_file}")
            return None

        if document_path is None:
            document_path = self._infer_document_path(annotation_file)

        if source_text is None and document_path is not None:
            source_text = self._read_document_text(document_path)

        if source_text is None:
            print(f"Warning: No source text available for {annotation_file}")
            return None

        sample_metadata: Dict[str, Any] = {}
        try:
            sample_metadata["annotation_file"] = str(
                annotation_file.resolve().relative_to(self.corpus_dir)
            )
        except (ValueError, FileNotFoundError):
            sample_metadata["annotation_file"] = str(annotation_file)

        if document_path:
            try:
                relative_doc = document_path.resolve().relative_to(self.corpus_dir)
                sample_metadata["document_path"] = str(relative_doc)
            except (ValueError, FileNotFoundError):
                sample_metadata["document_path"] = str(document_path)
            sample_metadata["source_file"] = str(document_path.name)
        else:
            sample_metadata["document_path"] = None

        for key, value in metadata.items():
            sample_metadata[key] = value

        # Drop None values for cleaner reporting
        sample_metadata = {k: v for k, v in sample_metadata.items() if v is not None}

        annotations = sorted(annotations, key=lambda item: item.get("start", 0))
        return source_text, annotations, sample_metadata

    # ------------------------------------------------------------------ loading

    def load_corpus_samples(self) -> List[InputSample]:
        """
        Load corpus documents and their ground-truth annotations.

        Returns:
            List of InputSample objects for Presidio evaluation.
        """
        if not self.annotations_dir.exists():
            raise FileNotFoundError(
                f"Annotations directory not found at {self.annotations_dir}. "
                "Run corpus generation before evaluation."
            )

        samples: List[InputSample] = []

        for annotation_file in sorted(self.annotations_dir.glob("*_annotations.json")):
            payload = self._load_annotation_payload(annotation_file)
            if payload is None:
                continue

            source_text, annotations, metadata = payload
            span_objects: List[Span] = []

            for record in annotations:
                try:
                    start = int(record["start"])
                    end = int(record["end"])
                    entity_type = record["entity_type"]
                except (KeyError, TypeError, ValueError):
                    continue

                if end <= start:
                    continue

                value = record.get("value")
                if not value:
                    value = source_text[start:end]

                span_objects.append(
                    Span(
                        entity_type=entity_type,
                        entity_value=value,
                        start_position=start,
                        end_position=end,
                    )
                )

            if not span_objects:
                print(f"Warning: No valid spans derived from {annotation_file}")
                continue

            sample = InputSample(
                full_text=source_text,
                spans=span_objects,
                metadata=metadata,
                create_tags_from_span=True,
            )
            samples.append(sample)

        return samples

    # ------------------------------------------------------------------ evaluate

    def evaluate_corpus(self) -> Dict[str, Any]:
        """
        Run evaluation on the entire corpus and return metrics.
        """
        print("Loading corpus samples...")
        samples = self.load_corpus_samples()

        if not samples:
            raise ValueError("No corpus samples found. Run corpus generation first.")

        print(f"Evaluating {len(samples)} documents...")

        evaluation_results = self.evaluator.evaluate_all(samples)
        aggregate_result = self.evaluator.calculate_score(evaluation_results)

        def metric(value: Optional[float]) -> float:
            if value is None:
                return 0.0
            if isinstance(value, float) and math.isnan(value):
                return 0.0
            return float(value)

        per_entity_metrics: Dict[str, Dict[str, Any]] = {}
        for entity, metrics in aggregate_result.per_type.items():
            if entity in (None, "O"):
                continue
            per_entity_metrics[entity] = {
                "precision": metric(metrics.precision),
                "recall": metric(metrics.recall),
                "f1": metric(metrics.f_beta),
                "support": metrics.num_annotated,
                "predicted": metrics.num_predicted,
                "true_positives": metrics.true_positives,
                "false_positives": metrics.false_positives,
                "false_negatives": metrics.false_negatives,
            }

        sample_breakdown: List[Dict[str, Any]] = []
        for sample, result in zip(samples, evaluation_results):
            sample_score = self.evaluator.calculate_score([result])
            sample_metadata = sample.metadata or {}
            sample_breakdown.append(
                {
                    "annotation_file": sample_metadata.get("annotation_file"),
                    "document_path": sample_metadata.get("document_path"),
                    "source_file": sample_metadata.get("source_file"),
                    "doc_type": sample_metadata.get("doc_type"),
                    "locale": sample_metadata.get("locale"),
                    "precision": metric(sample_score.pii_precision),
                    "recall": metric(sample_score.pii_recall),
                    "f1": metric(sample_score.pii_f),
                    "true_positives": sample_score.pii_true_positives or 0,
                    "false_positives": sample_score.pii_false_positives or 0,
                    "false_negatives": sample_score.pii_false_negatives or 0,
                    "entities_detected": sample_score.pii_predicted or 0,
                    "entities_expected": sample_score.pii_annotated or 0,
                }
            )

        overall_counts = {
            "precision": metric(aggregate_result.pii_precision),
            "recall": metric(aggregate_result.pii_recall),
            "f1": metric(aggregate_result.pii_f),
            "true_positives": aggregate_result.pii_true_positives or 0,
            "false_positives": aggregate_result.pii_false_positives or 0,
            "false_negatives": aggregate_result.pii_false_negatives or 0,
            "annotated": aggregate_result.pii_annotated or 0,
            "predicted": aggregate_result.pii_predicted or 0,
        }

        # Aggregate corpus summary information.
        doc_type_counts: Dict[str, int] = {}
        locale_counts: Dict[str, int] = {}
        for sample in samples:
            metadata = sample.metadata or {}
            doc_type = metadata.get("doc_type")
            locale = metadata.get("locale")
            if doc_type:
                doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
            if locale:
                locale_counts[locale] = locale_counts.get(locale, 0) + 1

        results: Dict[str, Any] = {
            "total_samples": len(samples),
            "model": "presidio-default",
            "metrics": {
                "overall": overall_counts
            },
            "per_entity": per_entity_metrics,
            "sample_breakdown": sample_breakdown,
            "corpus_summary": {
                "doc_type_counts": doc_type_counts,
                "locale_counts": locale_counts,
            },
        }

        metadata_file = self.corpus_dir / "corpus_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as handle:
                results["corpus_metadata"] = json.load(handle)

        return results

    # ------------------------------------------------------------------- export

    def save_baseline_report(self, results: Dict[str, Any], output_path: str) -> None:
        """Persist evaluation results to disk."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)

        print(f"Baseline report saved to: {output}")


if __name__ == "__main__":  # pragma: no cover - CLI utility
    evaluator = PresidioEvaluator(corpus_dir="data/corpus")
    evaluation_results = evaluator.evaluate_corpus()

    output_path = "cmos/reports/sprint-01/presidio_corpus_baseline.json"
    evaluator.save_baseline_report(evaluation_results, output_path)

    overall = evaluation_results["metrics"]["overall"]
    print("\nEvaluation Summary:")
    print(f"Overall Precision: {overall['precision']:.4f}")
    print(f"Overall Recall: {overall['recall']:.4f}")
    print(f"Overall F1: {overall['f1']:.4f}")
