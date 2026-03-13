# ABOUTME: External service adapters conforming to port protocols.
# ABOUTME: Wraps OpenAI and Qdrant clients for embedding, LLM, and vector operations.

from app.adapters.external.openai_embedding import OpenAIEmbeddingAdapter
from app.adapters.external.openai_llm import OpenAILLMAdapter
from app.adapters.external.qdrant_vectordb import QdrantVectorDBAdapter

__all__ = [
    "OpenAIEmbeddingAdapter",
    "QdrantVectorDBAdapter",
    "OpenAILLMAdapter",
]
