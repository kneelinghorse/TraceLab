"""Tests for the synthesize API endpoint."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.project import Project
from app.core.database import SessionLocal


def _create_test_project(db_session) -> Project:
    """Create a test project."""
    project = Project(name="Synthesis Test Project", description="For testing synthesis")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _create_test_document(db_session, project_id: uuid.UUID, name: str = "Test Document") -> Document:
    """Create a test document."""
    doc = Document(
        project_id=project_id,
        name=name,
        file_type="report",
        source_type="report",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _create_test_chunk(
    db_session, document_id: uuid.UUID, index: int = 0, content: str = "Test chunk content"
) -> DocumentChunk:
    """Create a test document chunk."""
    from sqlalchemy import text

    chunk = DocumentChunk(
        document_id=document_id,
        chunk_index=index,
        content=content,
        content_tsv=text("''"),
        token_count=len(content.split()),
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def _create_test_collection(db_session, name: str = "Test Collection") -> Collection:
    """Create a test collection."""
    collection = Collection(name=name, description="Test collection for synthesis")
    db_session.add(collection)
    db_session.commit()
    db_session.refresh(collection)
    return collection


def _add_chunk_to_collection(db_session, collection_id: str, chunk_id: str) -> CollectionItem:
    """Add a chunk to a collection."""
    item = CollectionItem(
        collection_id=collection_id,
        chunk_id=chunk_id,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _mock_openai_response(content: str = "This is a synthesis [1] with citations [2]."):
    """Create a mock OpenAI response."""
    mock_choice = MagicMock()
    mock_choice.message.content = content

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 500
    mock_usage.completion_tokens = 100
    mock_usage.total_tokens = 600

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    return mock_response


class TestSynthesizeEndpoint:
    """Tests for POST /api/v1/synthesize endpoint."""

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_collection_success(self, mock_openai_class, auth_headers, db_session):
        """Test successful synthesis from a collection."""
        client = TestClient(app)

        # Setup mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            "The documents discuss key findings [1] and supporting evidence [2]."
        )
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id, "Research Report")
        chunk1 = _create_test_chunk(db_session, document.id, 0, "First chunk with important findings.")
        chunk2 = _create_test_chunk(db_session, document.id, 1, "Second chunk with supporting data.")
        collection = _create_test_collection(db_session, "Research Collection")
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk1.id))
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk2.id))

        # Make request
        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": str(collection.id), "format": "summary"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert "content" in data
        assert "[1]" in data["content"] or "[2]" in data["content"]
        assert data["chunk_count"] == 2
        assert "tokens_used" in data
        assert data["truncated"] is False
        assert isinstance(data["citations"], list)

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_chunk_ids_success(self, mock_openai_class, auth_headers, db_session):
        """Test successful synthesis from specific chunk IDs."""
        client = TestClient(app)

        # Setup mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            "Summary based on provided chunks [1]."
        )
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk1 = _create_test_chunk(db_session, document.id, 0, "Chunk one content.")
        chunk2 = _create_test_chunk(db_session, document.id, 1, "Chunk two content.")

        # Make request
        response = client.post(
            "/api/v1/synthesize",
            json={"chunk_ids": [str(chunk1.id), str(chunk2.id)], "format": "bullets"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert "content" in data
        assert data["chunk_count"] == 2

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_with_custom_prompt(self, mock_openai_class, auth_headers, db_session):
        """Test synthesis with a custom prompt instruction."""
        client = TestClient(app)

        # Setup mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            "Executive summary: Key points from analysis [1]."
        )
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Analysis data.")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk.id))

        # Make request with custom prompt
        response = client.post(
            "/api/v1/synthesize",
            json={
                "collection_id": str(collection.id),
                "prompt": "Write an executive summary focusing on key findings.",
                "format": "report",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert "content" in data

    def test_synthesize_missing_source_validation(self, auth_headers):
        """Test that request fails when neither collection_id nor chunk_ids provided."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/synthesize",
            json={"format": "summary"},
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error
        assert "collection_id" in response.text.lower() or "chunk_ids" in response.text.lower()

    def test_synthesize_both_sources_validation(self, auth_headers):
        """Test that request fails when both collection_id and chunk_ids provided."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/synthesize",
            json={
                "collection_id": str(uuid.uuid4()),
                "chunk_ids": [str(uuid.uuid4())],
                "format": "summary",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error
        assert "both" in response.text.lower() or "either" in response.text.lower()

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_collection_not_found(self, mock_openai_class, auth_headers):
        """Test 400 error when collection doesn't exist."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        fake_id = str(uuid.uuid4())
        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": fake_id},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_empty_collection(self, mock_openai_class, auth_headers, db_session):
        """Test synthesis with empty collection returns appropriate message."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Create empty collection
        collection = _create_test_collection(db_session, "Empty Collection")

        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": str(collection.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chunk_count"] == 0
        assert "empty" in data["content"].lower() or "no content" in data["content"].lower()
        assert data["tokens_used"] == 0

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_chunks_not_found(self, mock_openai_class, auth_headers):
        """Test synthesis with non-existent chunk IDs returns empty response."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        fake_chunk_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        response = client.post(
            "/api/v1/synthesize",
            json={"chunk_ids": fake_chunk_ids},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chunk_count"] == 0

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_citations_extracted(self, mock_openai_class, auth_headers, db_session):
        """Test that citations are properly extracted from LLM response."""
        client = TestClient(app)

        # Setup mock with citations for first two chunks
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            "The analysis shows [1] important trends. Supporting data confirms [2] these findings. "
            "Additionally [1] confirms the pattern."
        )
        mock_openai_class.return_value = mock_client

        # Create test data with 2 chunks
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id, "Multi-Source Doc")
        chunk1 = _create_test_chunk(db_session, document.id, 0, "First source content here.")
        chunk2 = _create_test_chunk(db_session, document.id, 1, "Second source content here.")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk1.id))
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk2.id))

        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": str(collection.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        citations = data["citations"]
        # Should have 2 unique citations extracted (markers [1] and [2])
        assert len(citations) == 2
        # Each citation should have the required fields
        for citation in citations:
            assert "chunk_id" in citation
            assert "excerpt" in citation
            assert "document_id" in citation

    @patch("app.services.synthesis.OpenAI")
    def test_synthesize_format_options(self, mock_openai_class, auth_headers, db_session):
        """Test all four format options work correctly."""
        client = TestClient(app)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        # Create test data
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Test content.")
        collection = _create_test_collection(db_session)
        _add_chunk_to_collection(db_session, str(collection.id), str(chunk.id))

        for format_type in ["markdown", "summary", "report", "bullets"]:
            response = client.post(
                "/api/v1/synthesize",
                json={"collection_id": str(collection.id), "format": format_type},
                headers=auth_headers,
            )
            assert response.status_code == 200, f"Failed for format: {format_type}"

    def test_synthesize_invalid_format(self, auth_headers):
        """Test that invalid format returns validation error."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": str(uuid.uuid4()), "format": "invalid_format"},
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_synthesize_requires_authentication(self):
        """Test that endpoint requires authentication."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/synthesize",
            json={"collection_id": str(uuid.uuid4())},
        )

        assert response.status_code == 401


class TestSynthesizeService:
    """Unit tests for SynthesisService."""

    @patch("app.services.synthesis.OpenAI")
    def test_service_truncation_handling(self, mock_openai_class, db_session):
        """Test that service properly handles truncation when too many chunks."""
        from app.services.synthesis import SynthesisService, MAX_CHUNKS_PER_REQUEST

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        service = SynthesisService(session_factory=SessionLocal, client=mock_client)

        # Create many chunks
        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)

        chunk_ids = []
        for i in range(MAX_CHUNKS_PER_REQUEST + 10):
            chunk = _create_test_chunk(db_session, document.id, i, f"Chunk {i} content.")
            chunk_ids.append(uuid.UUID(str(chunk.id)))

        result = service.synthesize(chunk_ids=chunk_ids)

        assert result["truncated"] is True
        assert result["chunk_count"] == MAX_CHUNKS_PER_REQUEST

    @patch("app.services.synthesis.OpenAI")
    def test_service_token_tracking(self, mock_openai_class, db_session):
        """Test that service tracks token usage."""
        mock_client = MagicMock()
        mock_response = _mock_openai_response()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        mock_cost_monitor = MagicMock()

        from app.services.synthesis import SynthesisService

        service = SynthesisService(
            session_factory=SessionLocal,
            client=mock_client,
            cost_monitor=mock_cost_monitor,
        )

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Test content.")

        result = service.synthesize(chunk_ids=[uuid.UUID(str(chunk.id))])

        assert result["tokens_used"] == 600  # From mock
        mock_cost_monitor.track_usage.assert_called_once()

    @patch("app.services.synthesis.OpenAI")
    def test_service_sets_reasoning_effort_for_gpt5_models(self, mock_openai_class, db_session):
        """Test GPT-5.1/5.2 chat requests pin reasoning_effort for temperature compatibility."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_openai_class.return_value = mock_client

        from app.services.synthesis import SynthesisService

        service = SynthesisService(
            session_factory=SessionLocal,
            client=mock_client,
            model="gpt-5.1",
            temperature=0.35,
            max_tokens=512,
        )

        project = _create_test_project(db_session)
        document = _create_test_document(db_session, project.id)
        chunk = _create_test_chunk(db_session, document.id, 0, "Compatibility test content.")

        service.synthesize(chunk_ids=[uuid.UUID(str(chunk.id))])

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-5.1"
        assert kwargs["reasoning_effort"] == "none"
        assert kwargs["temperature"] == 0.35
        assert kwargs["max_completion_tokens"] == 512


class TestSynthesizeSchemas:
    """Tests for Pydantic request/response schemas."""

    def test_request_validation_collection_id(self):
        """Test request schema accepts valid collection_id."""
        from app.schemas.synthesis import SynthesizeRequest

        request = SynthesizeRequest(collection_id=uuid.uuid4())
        assert request.collection_id is not None
        assert request.chunk_ids is None

    def test_request_validation_chunk_ids(self):
        """Test request schema accepts valid chunk_ids."""
        from app.schemas.synthesis import SynthesizeRequest

        request = SynthesizeRequest(chunk_ids=[uuid.uuid4(), uuid.uuid4()])
        assert request.chunk_ids is not None
        assert len(request.chunk_ids) == 2
        assert request.collection_id is None

    def test_request_validation_neither_provided(self):
        """Test request schema rejects when neither source provided."""
        from app.schemas.synthesis import SynthesizeRequest

        with pytest.raises(ValueError, match="Either collection_id or chunk_ids"):
            SynthesizeRequest()

    def test_request_validation_both_provided(self):
        """Test request schema rejects when both sources provided."""
        from app.schemas.synthesis import SynthesizeRequest

        with pytest.raises(ValueError, match="either|both"):
            SynthesizeRequest(
                collection_id=uuid.uuid4(),
                chunk_ids=[uuid.uuid4()],
            )

    def test_request_validation_empty_chunk_ids(self):
        """Test request schema rejects empty chunk_ids list."""
        from app.schemas.synthesis import SynthesizeRequest

        with pytest.raises(ValueError, match="Either collection_id or chunk_ids"):
            SynthesizeRequest(chunk_ids=[])

    def test_response_schema_structure(self):
        """Test response schema has all required fields."""
        from app.schemas.synthesis import SynthesizeResponse, CitationInfo

        response = SynthesizeResponse(
            content="Test content [1]",
            citations=[
                CitationInfo(
                    chunk_id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    excerpt="First 100 chars...",
                )
            ],
            tokens_used=500,
            truncated=False,
            chunk_count=1,
        )

        assert response.content == "Test content [1]"
        assert len(response.citations) == 1
        assert response.tokens_used == 500
        assert response.truncated is False
        assert response.chunk_count == 1
