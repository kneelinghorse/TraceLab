"""Focused Qdrant deletion contract for failed document compensation."""

from unittest.mock import MagicMock

from app.services.qdrant_service import QdrantService


def test_delete_chunks_uses_exact_document_payload_filter() -> None:
    """Compensation must delete only vectors owned by the failed document."""
    mock_client = MagicMock()
    service = QdrantService(
        client=mock_client,
        collection_name="research_chunks",
        vector_size=3,
    )

    service.delete_chunks("document-123")

    mock_client.delete.assert_called_once()
    kwargs = mock_client.delete.call_args.kwargs
    assert kwargs["collection_name"] == "research_chunks"
    assert kwargs["wait"] is True
    selector = kwargs["points_selector"]
    assert len(selector.must) == 1
    assert selector.must[0].key == "document_id"
    assert selector.must[0].match.value == "document-123"
