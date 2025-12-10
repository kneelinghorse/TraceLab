"""Tests for Qdrant connection pre-warming functionality.

Tests the core pre-warming module at app/core/qdrant_client.py and
verifies the health check endpoints at app/api/v1/health.py.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestQdrantClientModule:
    """Tests for app.core.qdrant_client module."""

    def test_get_qdrant_client_returns_singleton(self):
        """Test that get_qdrant_client returns the same instance on repeated calls."""
        # Reset singleton state first
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        with patch.object(qc_module, 'QdrantClient') as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            # First call creates client
            client1 = qc_module.get_qdrant_client()

            # Second call returns same instance
            client2 = qc_module.get_qdrant_client()

            assert client1 is client2
            # Client class should only be instantiated once
            mock_client_class.assert_called_once()

        # Clean up
        qc_module.reset_client()

    def test_get_qdrant_client_validates_url(self):
        """Test that get_qdrant_client raises error when URL not configured."""
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        with patch('app.core.qdrant_client.settings') as mock_settings:
            mock_settings.qdrant_url = ""

            with pytest.raises(ValueError, match="QDRANT_URL must be configured"):
                qc_module.get_qdrant_client()

        qc_module.reset_client()

    def test_get_qdrant_client_validates_https_with_api_key(self):
        """Test that HTTPS is required when API key is set."""
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        with patch('app.core.qdrant_client.settings') as mock_settings:
            mock_settings.qdrant_url = "http://insecure.example.com"
            mock_settings.qdrant_api_key = "secret-key"

            with pytest.raises(ValueError, match="QDRANT_URL must use HTTPS"):
                qc_module.get_qdrant_client()

        qc_module.reset_client()

    @pytest.mark.asyncio
    async def test_prewarm_qdrant_success(self):
        """Test successful pre-warm operation."""
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "research_chunks"
        mock_collections = MagicMock()
        mock_collections.collections = [mock_collection]
        mock_client.get_collections.return_value = mock_collections
        mock_client.search.return_value = []

        with patch.object(qc_module, 'get_qdrant_client', return_value=mock_client):
            with patch('app.core.qdrant_client.settings') as mock_settings:
                mock_settings.qdrant_collection_name = "research_chunks"
                mock_settings.openai_embedding_dimension = 1536

                result = await qc_module.prewarm_qdrant()

        assert result is True
        assert qc_module.is_qdrant_ready() is True
        mock_client.get_collections.assert_called_once()
        mock_client.search.assert_called_once()

        qc_module.reset_client()

    @pytest.mark.asyncio
    async def test_prewarm_qdrant_missing_collection(self):
        """Test pre-warm when collection doesn't exist yet."""
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        mock_client = MagicMock()
        mock_collections = MagicMock()
        mock_collections.collections = []  # No collections
        mock_client.get_collections.return_value = mock_collections

        with patch.object(qc_module, 'get_qdrant_client', return_value=mock_client):
            with patch('app.core.qdrant_client.settings') as mock_settings:
                mock_settings.qdrant_collection_name = "research_chunks"

                result = await qc_module.prewarm_qdrant()

        # Should succeed but skip search (collection doesn't exist)
        assert result is True
        mock_client.get_collections.assert_called_once()
        mock_client.search.assert_not_called()

        qc_module.reset_client()

    @pytest.mark.asyncio
    async def test_prewarm_qdrant_failure(self):
        """Test pre-warm returns False on connection failure."""
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        mock_client = MagicMock()
        mock_client.get_collections.side_effect = Exception("Connection refused")

        with patch.object(qc_module, 'get_qdrant_client', return_value=mock_client):
            result = await qc_module.prewarm_qdrant()

        assert result is False
        assert qc_module.is_qdrant_ready() is False

        qc_module.reset_client()

    def test_get_qdrant_health_success(self):
        """Test health check returns correct status on success."""
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        mock_client = MagicMock()
        mock_col1 = MagicMock()
        mock_col1.name = "collection1"
        mock_col2 = MagicMock()
        mock_col2.name = "collection2"
        mock_collections = MagicMock()
        mock_collections.collections = [mock_col1, mock_col2]
        mock_client.get_collections.return_value = mock_collections

        with patch.object(qc_module, 'get_qdrant_client', return_value=mock_client):
            with patch('app.core.qdrant_client.settings') as mock_settings:
                mock_settings.qdrant_url = "http://localhost:6333"

                health = qc_module.get_qdrant_health()

        assert health["status"] == "healthy"
        assert health["collections_count"] == 2
        assert "collection1" in health["collections"]
        assert "collection2" in health["collections"]

        qc_module.reset_client()

    def test_get_qdrant_health_failure(self):
        """Test health check returns unhealthy on error."""
        from app.core import qdrant_client as qc_module
        qc_module.reset_client()

        with patch.object(qc_module, 'get_qdrant_client', side_effect=Exception("Connection error")):
            with patch('app.core.qdrant_client.settings') as mock_settings:
                mock_settings.qdrant_url = "http://localhost:6333"

                health = qc_module.get_qdrant_health()

        assert health["status"] == "unhealthy"
        assert "Connection error" in health["error"]

        qc_module.reset_client()

    def test_reset_client_clears_state(self):
        """Test reset_client properly clears singleton and pre-warm state."""
        from app.core import qdrant_client as qc_module

        # Set up some state
        qc_module._client = MagicMock()
        qc_module._is_prewarmed = True

        # Reset
        qc_module.reset_client()

        assert qc_module._client is None
        assert qc_module._is_prewarmed is False


class TestHealthEndpoints:
    """Tests for health check API endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test basic health endpoint returns healthy."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_qdrant_health_endpoint_success(self):
        """Test /health/qdrant returns healthy when Qdrant is available."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        # Patch where the function is imported/used, not where it's defined
        with patch('app.api.v1.health.get_qdrant_health') as mock_health:
            mock_health.return_value = {
                "status": "healthy",
                "prewarmed": True,
                "collections_count": 2,
                "collections": ["col1", "col2"],
                "url": "http://localhost:6333",
            }

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/health/qdrant")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["prewarmed"] is True

    @pytest.mark.asyncio
    async def test_qdrant_health_endpoint_failure(self):
        """Test /health/qdrant returns 503 when Qdrant is unavailable."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        # Patch where the function is imported/used
        with patch('app.api.v1.health.get_qdrant_health') as mock_health:
            mock_health.return_value = {
                "status": "unhealthy",
                "prewarmed": False,
                "error": "Connection refused",
                "url": "http://localhost:6333",
            }

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/health/qdrant")

            assert response.status_code == 503
            data = response.json()["detail"]
            assert data["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_readiness_endpoint_all_healthy(self):
        """Test /health/ready returns ready when all services healthy."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        from app.core.database import get_db

        # Mock DB session
        class FakeResult:
            def fetchone(self):
                return (1,)

        class FakeSession:
            def execute(self, _query):
                return FakeResult()

            def close(self):
                pass

        def _get_db():
            yield FakeSession()

        app.dependency_overrides[get_db] = _get_db

        try:
            # Patch where functions are imported/used
            with patch('app.api.v1.health.get_qdrant_health') as mock_health:
                with patch('app.api.v1.health.is_qdrant_ready', return_value=True):
                    mock_health.return_value = {
                        "status": "healthy",
                        "prewarmed": True,
                        "collections_count": 1,
                        "collections": ["col1"],
                        "url": "http://localhost:6333",
                    }

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/api/v1/health/ready")

                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "ready"
                    assert data["database"] == "healthy"
                    assert data["qdrant"] == "healthy"
                    assert data["qdrant_prewarmed"] is True
        finally:
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_readiness_endpoint_qdrant_unhealthy(self):
        """Test /health/ready returns 503 when Qdrant is unhealthy."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        from app.core.database import get_db

        # Mock DB session
        class FakeResult:
            def fetchone(self):
                return (1,)

        class FakeSession:
            def execute(self, _query):
                return FakeResult()

            def close(self):
                pass

        def _get_db():
            yield FakeSession()

        app.dependency_overrides[get_db] = _get_db

        try:
            # Patch where functions are imported/used
            with patch('app.api.v1.health.get_qdrant_health') as mock_health:
                with patch('app.api.v1.health.is_qdrant_ready', return_value=False):
                    mock_health.return_value = {
                        "status": "unhealthy",
                        "prewarmed": False,
                        "error": "Connection refused",
                        "url": "http://localhost:6333",
                    }

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/api/v1/health/ready")

                    assert response.status_code == 503
                    data = response.json()["detail"]
                    assert data["status"] == "not_ready"
                    assert "Qdrant" in data["errors"][0]
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestServiceIntegration:
    """Tests for service integration with shared client."""

    def test_qdrant_service_uses_shared_client(self):
        """Test QdrantService uses shared client by default."""
        from app.core import qdrant_client as qc_module

        qc_module.reset_client()

        mock_client = MagicMock()
        # Patch where it's imported in the service module
        with patch('app.services.qdrant_service.get_qdrant_client', return_value=mock_client):
            from app.services.qdrant_service import QdrantService
            service = QdrantService()

        assert service.client is mock_client
        qc_module.reset_client()

    def test_qdrant_service_accepts_custom_client(self):
        """Test QdrantService can use a custom client for testing."""
        from app.services.qdrant_service import QdrantService

        custom_client = MagicMock()
        service = QdrantService(client=custom_client)

        assert service.client is custom_client

    def test_semantic_cache_uses_shared_client(self):
        """Test SemanticCacheService uses shared client by default."""
        from app.core import qdrant_client as qc_module

        qc_module.reset_client()

        mock_client = MagicMock()
        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections

        # Patch where it's imported in the service module
        with patch('app.services.semantic_cache.get_qdrant_client', return_value=mock_client):
            from app.services.semantic_cache import SemanticCacheService
            # Disable to avoid collection creation
            service = SemanticCacheService(enabled=False)

        assert service._client is mock_client
        qc_module.reset_client()

    def test_semantic_cache_accepts_custom_client(self):
        """Test SemanticCacheService can use a custom client for testing."""
        from app.services.semantic_cache import SemanticCacheService

        custom_client = MagicMock()
        # Disable to avoid collection creation
        service = SemanticCacheService(client=custom_client, enabled=False)

        assert service._client is custom_client
