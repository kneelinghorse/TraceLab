"""Submit-time lint gate for mission authoring (T40.3).

Enforces contract-shape quality at the moment a mission transitions from
draft → queued, catching thin missions before they hit DeepSearch's smoke
pipeline. The rule set mirrors DeepSearch's own detection regex so both
sides of the contract agree about what counts as "structural" vs.
"underspecified."

Pluggable by design: each rule is a small class implementing :meth:`check`.
The linter fans out over the registered rule set and partitions violations
into errors (hard-fail, 422) and warnings (soft, 200 with surfaced list).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Protocol

# ---------------------------------------------------------------------------
# Regex mirrors (align with DeepSearch's _is_structural_success_criterion).
# Keep in sync if the DeepSearch team revises the set.
# ---------------------------------------------------------------------------

# Structural-output phrases. Match as whole phrases where possible.
_STRUCTURAL_OUTPUT_RE = re.compile(
    r"\b("
    r"executive\s+summary"
    r"|comparison\s+table"
    r"|matrix"
    r"|markdown"
    r"|columns?"
    r"|sections?"
    r"|headings?"
    r")\b",
    re.IGNORECASE,
)

# Distributive phrasing. "each X", "every Y", "per Z", "for each Z".
_DISTRIBUTIVE_RE = re.compile(
    r"\b(for\s+each|each|every|per)\s+\w+",
    re.IGNORECASE,
)

# Exclusion-intent language. If any of these fire in prose but
# excluded_entities is empty, the author said "exclude X" without telling
# DeepSearch which X to exclude.
_EXCLUSION_LANGUAGE_RE = re.compile(
    r"\b("
    r"exclud\w*"           # exclude / excluded / excluding / exclusion
    r"|ignore"
    r"|don'?t\s+include"
    r"|do\s+not\s+include"
    r"|without"
    r")\b",
    re.IGNORECASE,
)

# Proper-noun candidate heuristic: a Title-Case token or all-caps acronym
# that is not a common sentence-starter word. We deliberately cast a wide
# net — this is only used to decide whether a mission has *some* named
# entities, not to enumerate them.
_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]{1,}(?:-[A-Z0-9][a-zA-Z0-9]*)*)\b")
# Words that frequently appear Title-Case at sentence start or in titles but
# don't actually name an entity. Kept conservative — we'd rather under-count
# proper nouns (triggering a warning/error that prompts the author to add
# required_entities) than pretend "Do" is a named entity.
_STOP_WORDS = frozenset(
    {
        # Determiners / articles
        "The",
        "This",
        "That",
        "These",
        "Those",
        "A",
        "An",
        "Another",
        # Pronouns
        "We",
        "I",
        "Our",
        "Your",
        "It",
        "They",
        "Their",
        "His",
        "Her",
        "My",
        # Prepositions / conjunctions
        "As",
        "At",
        "By",
        "For",
        "From",
        "In",
        "Of",
        "On",
        "Or",
        "To",
        "Up",
        "With",
        "Without",
        "Through",
        "Between",
        "Across",
        "After",
        "Before",
        "Since",
        "Until",
        "Among",
        "Over",
        "Under",
        "And",
        "But",
        "So",
        "If",
        "Because",
        # Wh-words
        "When",
        "Where",
        "Why",
        "How",
        "What",
        "Which",
        "Who",
        # Common auxiliary / action verbs that often start sentences
        "Be",
        "Is",
        "Are",
        "Was",
        "Were",
        "Has",
        "Have",
        "Had",
        "Do",
        "Does",
        "Did",
        "Can",
        "Could",
        "Will",
        "Would",
        "Should",
        "May",
        "Might",
        "Must",
        "Shall",
        # Common imperative verbs that lead research objectives
        "Analyze",
        "Summarize",
        "Compare",
        "Describe",
        "Explain",
        "Research",
        "Investigate",
        "Explore",
        "Review",
        "Evaluate",
        "Identify",
        "Document",
        "Find",
        "List",
        "Show",
        "Write",
        "Produce",
        "Build",
        "Create",
        "Generate",
        "Return",
        "Cover",
        "Gather",
        "Collect",
        "Map",
        "Rank",
        "Report",
        "Determine",
        "Assess",
        # Generic nouns and adjectives that often appear Title-Case in test fixtures
        "Test",
        "Mission",
        "Analysis",
    }
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintViolation:
    rule: str
    field: str
    message: str
    suggestion: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "rule": self.rule,
            "field": self.field,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class LintResult:
    errors: list[LintViolation]
    warnings: list[LintViolation]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


class LintRule(Protocol):
    name: str
    severity: str  # "error" | "warning"

    def check(self, mission) -> list[LintViolation]: ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_prose(*parts: object) -> str:
    pieces: list[str] = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, str):
            pieces.append(p)
        elif isinstance(p, (list, tuple)):
            for item in p:
                if isinstance(item, str):
                    pieces.append(item)
                elif isinstance(item, dict):
                    # e.g. references = [{title: ...}]
                    title = item.get("title") if isinstance(item.get("title"), str) else None
                    if title:
                        pieces.append(title)
        elif isinstance(p, dict):
            for v in p.values():
                if isinstance(v, str):
                    pieces.append(v)
    return "\n".join(pieces)


_SENTENCE_BOUNDARY_RE = re.compile(r"(?:^|[.!?\n]\s*)")


def _proper_noun_candidates(text: str) -> set[str]:
    """Extract Title-Case tokens likely to be real named entities.

    Drops tokens that appear at sentence start (where capitalization is
    grammatical, not semantic) and filters a small stop list. Under-counts
    on purpose — we'd rather push authors toward required_entities than
    pretend 'Summarize' is a named entity.
    """
    # Mask out the first word of each sentence so those tokens don't count.
    # Walk sentences via the boundary regex, keep everything except each
    # sentence's leading word.
    cleaned_parts: list[str] = []
    for piece in _SENTENCE_BOUNDARY_RE.split(text):
        if not piece:
            continue
        words = piece.split(maxsplit=1)
        if len(words) == 2:
            cleaned_parts.append(words[1])
        # else: single-word sentence → skip entirely

    cleaned = " ".join(cleaned_parts)
    return {
        token
        for token in _PROPER_NOUN_RE.findall(cleaned)
        if token not in _STOP_WORDS
    }


def _list_or_none(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class DistributivePhrasingNeedsEntities:
    """Hard rule: if success_criteria uses distributive phrasing ('each X'),
    the mission must declare required_entities OR include at least 2 proper
    nouns in title / objective / deliverables that DeepSearch can latch onto.
    """

    name = "distributive-phrasing-needs-entities"
    severity = "error"

    def check(self, mission) -> list[LintViolation]:
        criteria = _list_or_none(getattr(mission, "success_criteria", None))
        matched_criteria = [c for c in criteria if isinstance(c, str) and _DISTRIBUTIVE_RE.search(c)]
        if not matched_criteria:
            return []

        required_entities = _list_or_none(getattr(mission, "required_entities", None))
        if required_entities:
            return []

        title_prose = _coerce_prose(
            getattr(mission, "title", None),
            getattr(mission, "objective", None),
            getattr(mission, "deliverables", None),
        )
        proper_nouns = _proper_noun_candidates(title_prose)
        if len(proper_nouns) >= 2:
            return []

        return [
            LintViolation(
                rule=self.name,
                field="success_criteria",
                message=(
                    "Success criteria use distributive phrasing ('each', 'every', "
                    "'per', 'for each') but the mission declares no required_entities "
                    f"and only {len(proper_nouns)} proper-noun candidate(s) in "
                    "title/objective/deliverables."
                ),
                suggestion=(
                    "Populate required_entities with the names the research must "
                    "cover, or rewrite the success criterion(ia) to name them "
                    "directly. Example match: "
                    f"'{matched_criteria[0][:80]}'"
                ),
            )
        ]


class StructuralOutputNeedsShape:
    """Hard rule: if success_criteria promises structural output (executive
    summary, comparison table, matrix, markdown, columns, sections,
    headings), the mission must declare deliverables OR expected_output_schema
    so DeepSearch knows what shape to synthesize.
    """

    name = "structural-output-needs-shape"
    severity = "error"

    def check(self, mission) -> list[LintViolation]:
        criteria = _list_or_none(getattr(mission, "success_criteria", None))
        matched = [c for c in criteria if isinstance(c, str) and _STRUCTURAL_OUTPUT_RE.search(c)]
        if not matched:
            return []

        deliverables = _list_or_none(getattr(mission, "deliverables", None))
        schema = getattr(mission, "expected_output_schema", None)
        if deliverables or (isinstance(schema, dict) and schema):
            return []

        return [
            LintViolation(
                rule=self.name,
                field="success_criteria",
                message=(
                    "Success criteria mention structural output forms (e.g. "
                    "'executive summary', 'comparison table', 'matrix') but the "
                    "mission has no deliverables and no expected_output_schema."
                ),
                suggestion=(
                    "Add deliverables describing the concrete artifacts, or attach "
                    "an expected_output_schema JSON object so DeepSearch can shape "
                    "the synthesized output."
                ),
            )
        ]


class ExclusionLanguageNeedsExcludedEntities:
    """Hard rule: if prose (objective, background, focus) uses exclusion
    language ('exclude X', 'ignore Y', 'without Z') but excluded_entities is
    empty, the author named an exclusion intent without telling DeepSearch
    which entities to exclude.
    """

    name = "exclusion-language-needs-excluded-entities"
    severity = "error"

    def check(self, mission) -> list[LintViolation]:
        excluded = _list_or_none(getattr(mission, "excluded_entities", None))
        if excluded:
            return []

        prose_fields = {
            "objective": getattr(mission, "objective", None),
            "background": getattr(mission, "background", None),
            "focus": getattr(mission, "focus", None),
        }
        for field_name, text in prose_fields.items():
            if not isinstance(text, str):
                continue
            match = _EXCLUSION_LANGUAGE_RE.search(text)
            if match:
                return [
                    LintViolation(
                        rule=self.name,
                        field=field_name,
                        message=(
                            f"{field_name} uses exclusion language "
                            f"('{match.group(0)}') but excluded_entities is empty."
                        ),
                        suggestion=(
                            "Populate excluded_entities with the specific names or "
                            "concepts DeepSearch should filter out."
                        ),
                    )
                ]
        return []


class BroadObjectiveNeedsEntities:
    """Soft rule: broad objective with zero named-or-required entities is a
    likely thin mission. Warn but don't block — some missions are genuinely
    exploratory.
    """

    name = "broad-objective-no-entities"
    severity = "warning"

    def check(self, mission) -> list[LintViolation]:
        required = _list_or_none(getattr(mission, "required_entities", None))
        if required:
            return []

        objective = getattr(mission, "objective", "") or ""
        if not isinstance(objective, str) or len(objective) < 80:
            # Short objectives are usually pointed enough not to need entities.
            return []

        proper_nouns = _proper_noun_candidates(objective)
        if len(proper_nouns) > 0:
            return []

        return [
            LintViolation(
                rule=self.name,
                field="objective",
                message=(
                    "Objective is long-form but declares no required_entities "
                    "and contains no proper nouns — DeepSearch may struggle to "
                    "anchor the research."
                ),
                suggestion=(
                    "Consider naming the specific entities, concepts, or sources "
                    "the research should cover in required_entities."
                ),
            )
        ]


DEFAULT_RULES: tuple[LintRule, ...] = (
    DistributivePhrasingNeedsEntities(),
    StructuralOutputNeedsShape(),
    ExclusionLanguageNeedsExcludedEntities(),
    BroadObjectiveNeedsEntities(),
)


def lint_mission_for_submit(
    mission, rules: Iterable[LintRule] | None = None
) -> LintResult:
    """Run every rule against the mission; partition into errors + warnings."""
    rules = rules if rules is not None else DEFAULT_RULES
    errors: list[LintViolation] = []
    warnings: list[LintViolation] = []
    for rule in rules:
        for violation in rule.check(mission):
            if rule.severity == "error":
                errors.append(violation)
            else:
                warnings.append(violation)
    return LintResult(errors=errors, warnings=warnings)
