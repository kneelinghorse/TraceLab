"""
Lightweight, dependency-free redaction service.

The original Presidio integration pulled in heavyweight analyzer/anonymizer
dependencies that are no longer required in the TraceLab stack. This module
provides a small regex/deny-list driven replacement so existing API surfaces
continue to function without external services.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_DENY_LIST_PATH = Path("config/redaction_deny_list.json")


@dataclass
class Pattern:
    """A minimal pattern representation used for recognizer compatibility."""

    name: str
    regex: str


class _SimpleRecognizer:
    """Detect entities using regexes plus optional deny-lists."""

    def __init__(
        self,
        supported_entity: str,
        patterns: Sequence[Pattern],
        deny_list: Optional[List[str]] = None,
    ) -> None:
        self.supported_entity = supported_entity
        self.patterns = list(patterns)
        self.deny_list = [value.strip() for value in (deny_list or []) if value]

    def find_matches(self, text: str) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for pattern in self.patterns:
            for match in re.finditer(pattern.regex, text, flags=re.IGNORECASE):
                matches.append(
                    {
                        "entity_type": self.supported_entity,
                        "text": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                        "source": pattern.name,
                    }
                )

        matches.extend(self._deny_matches(text))
        return matches

    def _deny_matches(self, text: str) -> List[Dict[str, Any]]:
        """Produce spans for explicit deny-list values."""
        if not self.deny_list:
            return []

        lowered = text.lower()
        spans: List[Dict[str, Any]] = []

        for token in self.deny_list:
            if not token:
                continue
            token_lower = token.lower()
            start = lowered.find(token_lower)
            while start != -1:
                spans.append(
                    {
                        "entity_type": self.supported_entity,
                        "text": text[start : start + len(token)],
                        "start": start,
                        "end": start + len(token),
                        "source": "deny_list",
                    }
                )
                start = lowered.find(token_lower, start + len(token))
        return spans


class ParticipantIDRecognizer(_SimpleRecognizer):
    """Recognizer for participant identifiers such as PID-2024-1234."""

    def __init__(self, deny_list: Optional[List[str]] = None) -> None:
        super().__init__(
            supported_entity="PARTICIPANT_ID",
            patterns=[
                Pattern("participant_id_standard", r"\bPID-\d{4}-\d{4}\b"),
                Pattern("participant_id_extended", r"\bPARTICIPANT-[A-Z0-9]+-\d{4}\b"),
                Pattern("participant_id_short", r"\bP-\d{4}-\d{4}\b"),
            ],
            deny_list=deny_list,
        )


class ProjectIDRecognizer(_SimpleRecognizer):
    """Recognizer for research project identifiers."""

    def __init__(self, deny_list: Optional[List[str]] = None) -> None:
        super().__init__(
            supported_entity="PROJECT_ID",
            patterns=[
                Pattern("project_id_standard", r"\bPROJ-[A-Z]+-\d{4}\b"),
                Pattern("project_id_extended", r"\bPROJECT-[A-Z]+-\d{4}\b"),
            ],
            deny_list=deny_list,
        )


class PresidioRedactionService:
    """Regex-based document redaction replacement for the retired Presidio stack."""

    _EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
    _PHONE_PATTERN = re.compile(
        r"(?:\+?\d{1,3}[\s\-\.]?)?(?:\(?\d{2,4}\)?[\s\-\.]?){2,4}(?:x\d{2,6})?"
    )

    def __init__(
        self,
        deny_list_path: Optional[str | Path] = None,
        ensure_spacy_model: bool = False,  # kept for backwards compatibility
        **_: Any,
    ) -> None:
        del ensure_spacy_model  # parameter retained for API compatibility

        self.deny_list_path = (
            Path(deny_list_path) if deny_list_path else DEFAULT_DENY_LIST_PATH
        )
        self._deny_lists = self._load_deny_lists(self.deny_list_path)
        self.recognizers = [
            ParticipantIDRecognizer(self._deny_lists.get("PARTICIPANT_ID")),
            ProjectIDRecognizer(self._deny_lists.get("PROJECT_ID")),
        ]

    def redact_document(
        self,
        text: str,
        document_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_pseudonymization: bool = True,
    ) -> Dict[str, Any]:
        """
        Perform lightweight redaction over known identifier patterns.

        Args:
            text: Raw document text.
            document_id: Optional identifier for audit trails.
            metadata: Arbitrary metadata persisted into audit trail.
            use_pseudonymization: Whether to replace entities with pseudo-values.
        """

        metadata = metadata or {}
        entities = self._detect_entities(text)
        replacements = self._build_replacements(entities, use_pseudonymization)
        redacted_text = self._apply_replacements(text, replacements)

        return {
            "redacted_text": redacted_text,
            "entities": entities,
            "audit_trail": {
                "document_id": document_id,
                "metadata": metadata,
                "deny_list_counts": self._count_deny_list_hits(entities),
                "redaction_performed": bool(replacements),
                "engine": "regex-stub",
            },
        }

    def _detect_entities(self, text: str) -> List[Dict[str, Any]]:
        entities: List[Dict[str, Any]] = []
        for recognizer in self.recognizers:
            entities.extend(recognizer.find_matches(text))

        entities.extend(self._match_common_entities(text))
        # Remove duplicate spans (same start/end/entity) while preserving order.
        seen: set[Tuple[str, int, int]] = set()
        unique: List[Dict[str, Any]] = []
        for entity in sorted(entities, key=lambda e: (e["start"], e["end"])):
            key = (entity["entity_type"], entity["start"], entity["end"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(entity)
        return unique

    def _match_common_entities(self, text: str) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for match in self._EMAIL_PATTERN.finditer(text):
            matches.append(
                {
                    "entity_type": "EMAIL_ADDRESS",
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "source": "email",
                }
            )
        for match in self._PHONE_PATTERN.finditer(text):
            normalized = re.sub(r"[\s\-\.]", "", match.group(0))
            if len(normalized) < 7:
                continue
            matches.append(
                {
                    "entity_type": "PHONE_NUMBER",
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "source": "phone",
                }
            )
        return matches

    def _build_replacements(
        self,
        entities: List[Dict[str, Any]],
        use_pseudonymization: bool,
    ) -> List[Tuple[int, int, str]]:
        replacements: List[Tuple[int, int, str]] = []
        for index, entity in enumerate(entities):
            placeholder = (
                self._pseudonym_for(entity["entity_type"], index)
                if use_pseudonymization
                else "[REDACTED]"
            )
            replacements.append((entity["start"], entity["end"], placeholder))
        return replacements

    @staticmethod
    def _apply_replacements(text: str, replacements: List[Tuple[int, int, str]]) -> str:
        if not replacements:
            return text
        replacements.sort(key=lambda span: span[0])
        pieces: List[str] = []
        cursor = 0
        for start, end, value in replacements:
            pieces.append(text[cursor:start])
            pieces.append(value)
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces)

    @staticmethod
    def _pseudonym_for(entity_type: str, index: int) -> str:
        return f"{entity_type}-PSEUDO-{index:04d}"

    def _count_deny_list_hits(self, entities: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entity in entities:
            deny_tokens = self._deny_lists.get(entity["entity_type"], [])
            if not deny_tokens:
                continue
            normalized = entity["text"].strip().lower()
            if any(normalized == token.strip().lower() for token in deny_tokens):
                counts[entity["entity_type"]] = counts.get(entity["entity_type"], 0) + 1
        return counts

    @staticmethod
    def _load_deny_lists(path: Path) -> Dict[str, List[str]]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            return {}

        if not isinstance(raw, dict):
            return {}

        cleaned: Dict[str, List[str]] = {}
        for key, value in raw.items():
            if isinstance(value, list):
                cleaned[str(key)] = [str(item) for item in value if item]
        return cleaned
