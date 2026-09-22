"""LIB-1 criterion 4, mutation-tested in both directions.

Provenance is the Librarian's integrity guarantee (decision #513): with world
knowledge and corpus claims in one reply, the citation is the only thing that
tells them apart. So a fabricated citation MUST fail and an uncited corpus claim
MUST fail, and both must fail on the server, independent of any prompt.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.schemas.librarian import AssistantReply, MissionDraft, ReplySegment
from app.services.librarian import (
    WITHHELD_TEXT,
    parse_draft,
    parse_reply,
    validate_provenance,
    withhold,
)

pytestmark = pytest.mark.unit

RETRIEVED = str(uuid.uuid4())
OTHER = str(uuid.uuid4())


def _reply(*segments: ReplySegment) -> AssistantReply:
    return AssistantReply(segments=list(segments))


class TestProvenanceValidator:
    def test_cited_corpus_claim_with_retrieved_evidence_passes(self):
        reply = _reply(ReplySegment(kind="corpus_claim", text="Three sources cover X.", citations=[RETRIEVED]))
        assert validate_provenance(reply, {RETRIEVED}) == []

    def test_prose_without_citations_passes(self):
        reply = _reply(ReplySegment(kind="prose", text="Onboarding research usually starts with the audience."))
        assert validate_provenance(reply, set()) == []

    def test_uncited_corpus_claim_fails(self):
        """Direction one: asserting something about the corpus with nothing to back it."""
        reply = _reply(ReplySegment(kind="corpus_claim", text="Your project already covers X.", citations=[]))
        violations = validate_provenance(reply, {RETRIEVED})
        assert [v.reason for v in violations] == ["uncited_corpus_claim"]
        assert violations[0].segment_index == 0

    def test_fabricated_citation_fails(self):
        """Direction two: a citation that was never returned by the tool in this turn."""
        reply = _reply(ReplySegment(kind="corpus_claim", text="Your project covers X.", citations=[OTHER]))
        violations = validate_provenance(reply, {RETRIEVED})
        assert [v.reason for v in violations] == ["unresolved_citation"]
        assert OTHER in violations[0].detail

    def test_fabricated_citation_on_prose_also_fails(self):
        """A citation is a claim of provenance wherever it appears; prose cannot smuggle one in."""
        reply = _reply(ReplySegment(kind="prose", text="Background.", citations=[OTHER]))
        assert [v.reason for v in validate_provenance(reply, {RETRIEVED})] == ["unresolved_citation"]

    def test_mixed_valid_and_fabricated_citations_fail(self):
        reply = _reply(ReplySegment(kind="corpus_claim", text="Claim.", citations=[RETRIEVED, OTHER]))
        violations = validate_provenance(reply, {RETRIEVED})
        assert len(violations) == 1
        assert RETRIEVED not in violations[0].detail
        assert OTHER in violations[0].detail

    def test_empty_retrieved_set_makes_every_citation_fabricated(self):
        """Planning mode: with no tool results, nothing can be cited, so nothing may be claimed."""
        reply = _reply(ReplySegment(kind="corpus_claim", text="Claim.", citations=[RETRIEVED]))
        assert [v.reason for v in validate_provenance(reply, set())] == ["unresolved_citation"]

    def test_only_offending_segments_are_withheld(self):
        reply = _reply(
            ReplySegment(kind="prose", text="Keep me."),
            ReplySegment(kind="corpus_claim", text="Drop me.", citations=[OTHER]),
            ReplySegment(kind="corpus_claim", text="Keep me too.", citations=[RETRIEVED]),
        )
        withheld = withhold(reply, validate_provenance(reply, {RETRIEVED}))
        assert [segment.kind for segment in withheld.segments] == ["prose", "withheld", "corpus_claim"]
        assert withheld.segments[1].text == WITHHELD_TEXT
        assert withheld.segments[1].citations == []
        assert "Drop me." not in json.dumps(withheld.model_dump())


class TestReplyParsing:
    def test_json_reply_is_parsed_into_segments(self):
        content = json.dumps(
            {
                "segments": [
                    {"kind": "prose", "text": "Hello", "citations": []},
                    {"kind": "corpus_claim", "text": "Cited", "citations": [RETRIEVED]},
                ],
                "suggested_action": "draft_mission",
            }
        )
        reply = parse_reply(content)
        assert [segment.kind for segment in reply.segments] == ["prose", "corpus_claim"]
        assert reply.segments[1].citations == [RETRIEVED]
        assert reply.suggested_action == "draft_mission"

    def test_fenced_json_is_accepted(self):
        content = "```json\n" + json.dumps({"segments": [{"kind": "prose", "text": "Hi"}]}) + "\n```"
        assert parse_reply(content).segments[0].text == "Hi"

    def test_unparseable_output_becomes_prose_never_a_claim(self):
        """Free text cannot be mistaken for a corpus claim: it carries no citations and is prose."""
        reply = parse_reply("Just talking, no JSON here.")
        assert len(reply.segments) == 1
        assert reply.segments[0].kind == "prose"
        assert reply.segments[0].citations == []
        assert reply.suggested_action is None

    def test_unknown_suggested_action_is_dropped(self):
        reply = parse_reply(json.dumps({"segments": [], "suggested_action": "delete_everything"}))
        assert reply.suggested_action is None


class TestDraftParsing:
    def test_valid_draft_parses_with_mission_constraints(self):
        draft = parse_draft(
            json.dumps(
                {
                    "mission_id": "ONBOARD-1",
                    "title": "Onboarding friction",
                    "objective": "Find where new users drop off during onboarding and why.",
                    "success_criteria": ["Name the top three drop-off points", "Cite two studies per point"],
                    "required_entities": ["onboarding", " activation "],
                    "constraints": None,
                }
            )
        )
        assert isinstance(draft, MissionDraft)
        assert draft.required_entities == ["onboarding", "activation"]
        assert draft.constraints is None
        assert draft.tags == []

    def test_mission_id_is_sanitised_to_the_mission_pattern(self):
        draft = parse_draft(
            json.dumps(
                {
                    "mission_id": " onboarding research!! #1 ",
                    "title": "Onboarding friction",
                    "objective": "Find where new users drop off during onboarding and why.",
                    "success_criteria": ["One criterion"],
                }
            )
        )
        assert draft.mission_id == "onboarding-research-1"

    def test_missing_mission_id_gets_a_generated_one(self):
        draft = parse_draft(
            json.dumps(
                {
                    "title": "Onboarding friction",
                    "objective": "Find where new users drop off during onboarding and why.",
                    "success_criteria": ["One criterion"],
                }
            )
        )
        assert draft.mission_id.startswith("LIB-")

    def test_invalid_draft_raises_the_same_errors_mission_create_would(self):
        with pytest.raises(ValueError) as excinfo:
            parse_draft(json.dumps({"mission_id": "X", "title": "ok", "objective": "short", "success_criteria": []}))
        message = str(excinfo.value)
        assert "objective" in message
        assert "success_criteria" in message
