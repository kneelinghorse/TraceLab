"""Embedding generation service using OpenAI."""
import time
from typing import List, Optional
from app.core.config import settings

try:  # pragma: no cover - defensive import for environments without OpenAI SDK
    from openai import OpenAI
    from openai import RateLimitError, APIError
except ModuleNotFoundError as exc:  # pragma: no cover
    OpenAI = None  # type: ignore
    RateLimitError = APIError = Exception  # type: ignore
    _openai_import_error = exc
else:
    _openai_import_error = None


class EmbeddingService:
    """Service for generating embeddings using OpenAI's embedding models."""
    
    def __init__(self):
        if _openai_import_error is not None:
            raise RuntimeError(
                "The OpenAI SDK is required for embedding generation. "
                "Install the 'openai' package from requirements.txt."
            ) from _openai_import_error
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment variables")
        
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embedding_model
        self.dimension = settings.openai_embedding_dimension
        
    def generate_embedding(self, text: str, retry_max: int = 3) -> List[float]:
        """
        Generate embedding for a single text with exponential backoff.
        
        Args:
            text: Text to embed
            retry_max: Maximum number of retry attempts
            
        Returns:
            Embedding vector as list of floats
        """
        for attempt in range(retry_max):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=text
                )
                return response.data[0].embedding
            except RateLimitError as e:
                if attempt < retry_max - 1:
                    wait_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                    time.sleep(wait_time)
                    continue
                raise
            except APIError as e:
                if attempt < retry_max - 1:
                    wait_time = (2 ** attempt) * 1
                    time.sleep(wait_time)
                    continue
                raise
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
        retry_max: int = 3
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches with exponential backoff.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process per batch (OpenAI supports up to 2048)
            retry_max: Maximum number of retry attempts per batch
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            for attempt in range(retry_max):
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch
                    )
                    batch_embeddings = [item.embedding for item in response.data]
                    all_embeddings.extend(batch_embeddings)
                    break  # Success, exit retry loop
                except RateLimitError as e:
                    if attempt < retry_max - 1:
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        time.sleep(wait_time)
                        continue
                    raise
                except APIError as e:
                    if attempt < retry_max - 1:
                        wait_time = (2 ** attempt) * 2
                        time.sleep(wait_time)
                        continue
                    raise
        
        return all_embeddings


# Singleton instance (lazy initialization)
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
