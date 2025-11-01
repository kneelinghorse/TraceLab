"""
Presidio Redaction Service

Integrates Microsoft Presidio with custom recognizers for UX research domain,
pseudonymization operators, and callable interface for document redaction.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from faker import Faker
from presidio_analyzer import (
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from app.services.presidio_evaluator import PresidioEvaluator

DEFAULT_DENY_LIST_PATH = Path("cmos/config/redaction_deny_list.json")


class ParticipantIDRecognizer(PatternRecognizer):
    """Custom recognizer for UX research participant IDs.
    
    Recognizes patterns like:
    - PID-2024-1234
    - PARTICIPANT-ABC-1234
    - P-2024-0001
    """
    
    def __init__(self, deny_list: Optional[List[str]] = None):
        patterns = [
            Pattern(
                name="participant_id_standard",
                regex=r"\b(PID-\d{4}-\d{4})\b",
                score=0.9
            ),
            Pattern(
                name="participant_id_extended",
                regex=r"\b(PARTICIPANT-[A-Z0-9]+-\d{4})\b",
                score=0.85
            ),
            Pattern(
                name="participant_id_short",
                regex=r"\b(P-\d{4}-\d{4})\b",
                score=0.85
            ),
        ]
        super().__init__(
            supported_entity="PARTICIPANT_ID",
            patterns=patterns,
            supported_language="en",
            deny_list=deny_list or []
        )


class ProjectIDRecognizer(PatternRecognizer):
    """Custom recognizer for research project IDs.
    
    Recognizes patterns like:
    - PROJ-ALPHA-1234
    - PROJ-DELTA-5678
    - PROJECT-BETA-9999
    """
    
    def __init__(self, deny_list: Optional[List[str]] = None):
        patterns = [
            Pattern(
                name="project_id_standard",
                regex=r"\b(PROJ-[A-Z]+-\d{4})\b",
                score=0.9
            ),
            Pattern(
                name="project_id_extended",
                regex=r"\b(PROJECT-[A-Z]+-\d{4})\b",
                score=0.85
            ),
        ]
        super().__init__(
            supported_entity="PROJECT_ID",
            patterns=patterns,
            supported_language="en",
            deny_list=deny_list or []
        )


class FlexiblePhoneRecognizer(PatternRecognizer):
    """Recognizer targeting international phone numbers with optional extensions."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="labeled_phone_with_extension",
                regex=r"(?:(?<=Phone[:\s])|(?<=Tel[:\s])|(?<=Contact[:\s]))(?:\+?\d{1,3}[\s\-\.]?)?(?:\(?\d{2,4}\)?[\s\-\.]?){2,4}(?:x\d{2,6})?",
                score=0.65,
            ),
            Pattern(
                name="global_phone_flexible",
                regex=r"\b(?:\+?\d{1,3}[\s\-\.]?)?(?:\(?\d{2,4}\)?[\s\-\.]?){2,4}(?:x\d{2,6})?\b",
                score=0.5,
            ),
        ]
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=patterns,
            supported_language="en",
            context=["Phone", "Tel", "Contact", "Number", "Call"],
        )


class PresidioRedactionService:
    """Presidio-based redaction service with custom recognizers and pseudonymization."""
    
    def __init__(
        self,
        spacy_model: str = "en_core_web_lg",
        locale: str = "en_US",
        analyzer_engine: Optional[AnalyzerEngine] = None,
        anonymizer_engine: Optional[AnonymizerEngine] = None,
        deny_list_path: Optional[str] = None,
        ensure_spacy_model: bool = True,
    ):
        """
        Initialize the redaction service.
        
        Args:
            spacy_model: spaCy model for NLP engine (default: en_core_web_lg)
            locale: Faker locale for pseudonymization (default: en_US)
            analyzer_engine: Optional pre-configured AnalyzerEngine (useful for tests)
            anonymizer_engine: Optional AnonymizerEngine instance
            deny_list_path: Optional path to JSON file containing entity deny-lists
            ensure_spacy_model: When True, attempts to download required spaCy model
        """
        self.spacy_model = spacy_model
        self.locale = locale
        self.deny_list_path = Path(deny_list_path) if deny_list_path else DEFAULT_DENY_LIST_PATH
        self._fake = Faker(locale)

        self._deny_lists = self._load_deny_lists(self.deny_list_path)

        # Ensure spaCy model is available
        if ensure_spacy_model:
            self._ensure_spacy_model(spacy_model)

        if analyzer_engine is None:
            # Configure NLP engine when analyzer is not supplied
            nlp_configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": spacy_model}],
            }
            provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
            nlp_engine = provider.create_engine()
            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        else:
            self.analyzer = analyzer_engine

        # Add custom recognizers when registry is available
        participant_recognizer = ParticipantIDRecognizer(
            deny_list=self._deny_lists.get("PARTICIPANT_ID")
        )
        project_recognizer = ProjectIDRecognizer(
            deny_list=self._deny_lists.get("PROJECT_ID")
        )
        registry: Optional[RecognizerRegistry] = getattr(self.analyzer, "registry", None)
        if registry and hasattr(registry, "add_recognizer"):
            registry.add_recognizer(participant_recognizer)
            registry.add_recognizer(project_recognizer)
            registry.add_recognizer(FlexiblePhoneRecognizer())

        # Initialize anonymizer
        self.anonymizer = anonymizer_engine or AnonymizerEngine()

        # Configure pseudonymization operators
        self._setup_pseudonymization_operators()

        # Attach lightweight post-processing to tighten span boundaries for priority entities.
        original_analyze = self.analyzer.analyze

        def analyze_with_post_processing(analyzer_self, *args, **kwargs):
            results = original_analyze(*args, **kwargs)
            text_arg = kwargs.get("text")
            if text_arg is None and args:
                text_arg = args[0]
            if isinstance(text_arg, str) and results:
                return self._refine_analyzer_results(text_arg, results)
            return results

        self.analyzer.analyze = analyze_with_post_processing.__get__(
            self.analyzer, self.analyzer.__class__
        )
    
    @staticmethod
    def _ensure_spacy_model(model_name: str) -> None:
        """Download the spaCy model if it is not already installed."""
        try:
            import spacy
            from spacy.util import is_package
            
            if not is_package(model_name):
                import spacy.cli
                print(f"Downloading spaCy model '{model_name}' for Presidio analyzer...")
                spacy.cli.download(model_name)
        except Exception as exc:
            print(f"Warning: Could not ensure spaCy model '{model_name}': {exc}")

    def _load_deny_lists(self, path: Path) -> Dict[str, List[str]]:
        """Load deny-list configuration from disk."""
        if not path:
            return {}
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            print(f"Warning: Unable to load deny list file at {path}: {exc}")
            return {}

        if not isinstance(payload, dict):
            return {}

        cleaned: Dict[str, List[str]] = {}
        for entity, values in payload.items():
            if isinstance(values, list):
                cleaned[entity] = [str(value) for value in values if value]
        return cleaned
    
    def _setup_pseudonymization_operators(self) -> None:
        """Configure Faker-based pseudonymization operators."""
        # Store operators for use in anonymization
        self._fake_name = lambda value, language="en": self._fake.name()
        self._fake_email = lambda value, language="en": self._fake.email()
        self._fake_phone = lambda value, language="en": self._fake.phone_number()
        self._fake_address = lambda value, language="en": self._fake.address()
        self._fake_location = lambda value, language="en": f"{self._fake.city()}, {self._fake.state()}"
        self._fake_date = lambda value, language="en": self._fake.date()
        self._fake_participant_id = lambda value, language="en": f"PID-{self._fake.year()}-{self._fake.random_int(1000, 9999)}"
        self._fake_project_id = lambda value, language="en": f"PROJ-{self._fake.word().upper()}-{self._fake.random_int(1000, 9999)}"
    
    def redact_document(
        self,
        text: str,
        document_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_pseudonymization: bool = True
    ) -> Dict[str, Any]:
        """
        Redact PII from a document text.
        
        Args:
            text: Document text to redact
            document_id: Optional document identifier
            metadata: Optional document metadata
            use_pseudonymization: If True, use pseudonymization; otherwise use replace operator
        
        Returns:
            Dictionary with:
            - redacted_text: Redacted text
            - entities: List of detected entities with positions
            - audit_trail: Summary of redaction operations
        """
        # Analyze text for PII
        analyzer_results = self.analyzer.analyze(text=text, language="en")
        
        # Prepare anonymization operators
        operators: Dict[str, OperatorConfig] = {}
        
        if use_pseudonymization:
            operators = {
                "PERSON": OperatorConfig("custom", {"lambda": self._fake_name}),
                "EMAIL_ADDRESS": OperatorConfig("custom", {"lambda": self._fake_email}),
                "PHONE_NUMBER": OperatorConfig("custom", {"lambda": self._fake_phone}),
                "LOCATION": OperatorConfig("custom", {"lambda": self._fake_location}),
                "DATE_TIME": OperatorConfig("custom", {"lambda": self._fake_date}),
                "PARTICIPANT_ID": OperatorConfig("custom", {"lambda": self._fake_participant_id}),
                "PROJECT_ID": OperatorConfig("custom", {"lambda": self._fake_project_id}),
            }
        else:
            # Default replace operator for entities without custom operators
            operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "<REDACTED>"})
        
        # Anonymize text
        anonymizer_results = self.anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators=operators
        )
        
        # Build entity list for audit trail
        entities = [
            {
                "entity_type": result.entity_type,
                "start": result.start,
                "end": result.end,
                "text": text[result.start:result.end],
                "score": result.score
            }
            for result in analyzer_results
        ]
        
        # Build audit trail
        audit_trail = {
            "document_id": document_id,
            "total_entities_detected": len(analyzer_results),
            "entities_by_type": self._count_entities_by_type(analyzer_results),
            "pseudonymization_enabled": use_pseudonymization,
            "spacy_model": self.spacy_model,
            "deny_list_counts": {entity: len(values) for entity, values in self._deny_lists.items()},
            "deny_list_source": str(self.deny_list_path) if self.deny_list_path else None,
            "metadata": metadata or {},
        }
        
        return {
            "redacted_text": anonymizer_results.text,
            "entities": entities,
            "audit_trail": audit_trail
        }
    
    def _count_entities_by_type(self, analyzer_results: List) -> Dict[str, int]:
        """Count entities by type."""
        counts: Dict[str, int] = {}
        for result in analyzer_results:
            entity_type = result.entity_type
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return counts

    # ------------------------------------------------------------------ post processing

    _TRIMMED_ENTITIES = {
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "PARTICIPANT_ID",
        "PROJECT_ID",
    }

    _TRAILING_CHARS = set(",.;:!?)]}\"'")
    _LEADING_MARKERS = set("-•·—–")
    _SEGMENT_SEPARATORS = ("\n", "\r", " - ", " – ", " — ", " • ", " | ", " / ")

    def _refine_analyzer_results(
        self, text: str, results: List[RecognizerResult]
    ) -> List[RecognizerResult]:
        """
        Normalize analyzer spans for priority entities to avoid trailing context
        (e.g., bullet labels) that create false negatives during evaluation.
        """
        refined: List[RecognizerResult] = []
        index_map: Dict[Tuple[str, int, int], int] = {}

        for result in results:
            if result.entity_type in self._TRIMMED_ENTITIES:
                start, end = self._normalize_entity_span(text, result.start, result.end)
                if start >= end:
                    continue
                if result.entity_type == "PHONE_NUMBER":
                    digits_only = re.sub(r"\D", "", text[start:end])
                    if len(digits_only) < 9:
                        continue
                candidate = RecognizerResult(
                    entity_type=result.entity_type,
                    start=start,
                    end=end,
                    score=result.score,
                    analysis_explanation=result.analysis_explanation,
                    recognition_metadata=getattr(result, "recognition_metadata", None),
                )
            else:
                candidate = result
                start, end = result.start, result.end

            key = (candidate.entity_type, start, end)
            existing_index = index_map.get(key)
            if existing_index is not None:
                if candidate.score > refined[existing_index].score:
                    refined[existing_index] = candidate
                continue

            index_map[key] = len(refined)
            refined.append(candidate)

        return refined

    def _normalize_entity_span(self, text: str, start: int, end: int) -> Tuple[int, int]:
        """
        Trim whitespace, bullet markers, and trailing context from a detected span.
        """
        # Guard against out-of-range indices
        text_length = len(text)
        start = max(0, min(start, text_length))
        end = max(0, min(end, text_length))
        if start >= end:
            return start, end

        # Trim leading whitespace.
        while start < end and text[start].isspace():
            start += 1

        # Trim leading markers such as bullets or dashes (often present in lists).
        while start < end and text[start] in self._LEADING_MARKERS:
            start += 1
            while start < end and text[start].isspace():
                start += 1

        # Trim trailing whitespace.
        while end > start and text[end - 1].isspace():
            end -= 1

        if start >= end:
            return start, end

        segment = text[start:end]

        # Split on common separators (newline, bullet indicator, etc.) and keep the first segment.
        for separator in self._SEGMENT_SEPARATORS:
            if separator in segment:
                segment = segment.split(separator)[0]
                break

        segment = segment.rstrip()

        # Remove trailing punctuation from the remaining segment.
        while segment and segment[-1] in self._TRAILING_CHARS:
            segment = segment[:-1]

        # Remove trailing markers such as closing parentheses that belong to surrounding text.
        while segment and segment[-1] in self._LEADING_MARKERS:
            segment = segment[:-1].rstrip()

        if not segment:
            return start, start

        end = start + len(segment)
        return start, end
    
    def run_regression_evaluation(
        self,
        corpus_dir: str = "data/corpus",
        baseline_report_path: Optional[str] = None,
        output_path: str = "cmos/reports/sprint-01/presidio_tuned_results.json"
    ) -> Dict[str, Any]:
        """
        Run regression evaluation comparing tuned configuration against baseline.
        
        Args:
            corpus_dir: Directory containing corpus files and annotations
            baseline_report_path: Path to baseline evaluation report (optional)
            output_path: Path to save comparison results
        
        Returns:
            Dictionary containing comparison metrics and deltas
        """
        # Run evaluation with tuned configuration (en_core_web_lg)
        evaluator = PresidioEvaluator(
            corpus_dir=corpus_dir,
            spacy_model=self.spacy_model,
            analyzer_engine=self.analyzer,
        )
        
        priority_entities = [
            "PERSON",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "PARTICIPANT_ID",
            "PROJECT_ID",
        ]

        print("Running regression evaluation with tuned Presidio configuration...")
        tuned_results = evaluator.evaluate_priority_entities(priority_entities)

        # Baseline evaluation using default analyzer unless an override artifact exists.
        baseline_results = self._load_baseline_report(baseline_report_path)
        if baseline_results is None or "per_entity" not in baseline_results:
            baseline_results = self._compute_priority_baseline(
                corpus_dir=corpus_dir,
                priority_entities=priority_entities,
            )

        comparison = {
            "tuned_configuration": {
                "spacy_model": self.spacy_model,
                "custom_recognizers": ["PARTICIPANT_ID", "PROJECT_ID"],
                "pseudonymization_enabled": True
            },
            "priority_entities": priority_entities,
            "tuned_metrics": tuned_results["metrics"],
            "per_entity_metrics": tuned_results["per_entity"],
        }

        if baseline_results:
            baseline_overall = baseline_results.get("metrics", {}).get("overall", {})
            tuned_overall = tuned_results["metrics"]["overall"]

            comparison["baseline_metrics"] = baseline_overall
            comparison["deltas"] = {
                "precision": tuned_overall["precision"] - baseline_overall.get("precision", 0.0),
                "recall": tuned_overall["recall"] - baseline_overall.get("recall", 0.0),
                "f1": tuned_overall["f1"] - baseline_overall.get("f1", 0.0),
            }
            comparison["improvement"] = {
                "precision_improved": comparison["deltas"]["precision"] > 0,
                "recall_improved": comparison["deltas"]["recall"] > 0,
                "f1_improved": comparison["deltas"]["f1"] > 0,
            }
            comparison["baseline_per_entity"] = baseline_results.get("per_entity", {})

        comparison["total_samples"] = tuned_results.get("total_samples", 0)

        # Save results
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2)
        
        print(f"Regression evaluation complete. Results saved to: {output}")
        
        return comparison

    # ------------------------------------------------------------------ helpers

    def _load_baseline_report(
        self,
        baseline_report_path: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Load existing baseline artifact if available."""
        if not baseline_report_path:
            return None

        report_path = Path(baseline_report_path)
        if not report_path.exists():
            return None

        try:
            with report_path.open("r", encoding="utf-8") as handle:
                payload: Dict[str, Any] = json.load(handle)
        except Exception as exc:
            print(f"Warning: Unable to read baseline report {baseline_report_path}: {exc}")
            return None

        if "per_entity" not in payload and "per_entity_metrics" in payload:
            payload["per_entity"] = payload["per_entity_metrics"]
        return payload

    def _compute_priority_baseline(
        self,
        corpus_dir: str,
        priority_entities: List[str],
        model_name: str = "en_core_web_sm",
    ) -> Dict[str, Any]:
        """
        Compute baseline metrics for priority entities, ensuring the required spaCy model exists.
        """
        def build_evaluator() -> PresidioEvaluator:
            return PresidioEvaluator(
                corpus_dir=corpus_dir,
                spacy_model=model_name,
            )

        try:
            evaluator = build_evaluator()
        except OSError:
            print(f"spaCy model '{model_name}' missing; attempting download...")
            self._ensure_spacy_model(model_name)
            try:
                evaluator = build_evaluator()
            except OSError as exc:
                raise RuntimeError(
                    f"Unable to load spaCy model '{model_name}'. "
                    "Install it manually with `python -m spacy download en_core_web_sm`."
                ) from exc

        return evaluator.evaluate_priority_entities(priority_entities)
