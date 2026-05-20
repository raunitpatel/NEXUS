"""
SentenceTransformer wrapper for the NEXUS Memory Agent.

Provides a singleton EmbeddingModel that loads all-MiniLM-L6-v2 once at
service startup and exposes a synchronous encode() method. The model runs
on CPU only (no GPU in Docker) and produces 384-dimension float vectors.

The model is loaded lazily on first call to EmbeddingModel() in main.py
lifespan to avoid import-time side effects during test collection.

Usage:
    model = EmbeddingModel()
    vector: list[float] = model.encode("some text to embed")
    # len(vector) == 384, each element is a Python float
"""

from __future__ import annotations

import structlog
from sentence_transformers import SentenceTransformer

from config import settings

logger = structlog.get_logger(__name__)


class EmbeddingModel:
    """
    Singleton wrapper around SentenceTransformer all-MiniLM-L6-v2.

    Loads the model from HuggingFace Hub on first instantiation (cached
    in ~/.cache/huggingface/ inside the container). Subsequent calls reuse
    the in-memory model — no re-loading between requests.

    Attributes:
        _model: The loaded SentenceTransformer instance.
        _dimensions: Expected output dimensions (384 for all-MiniLM-L6-v2).
    """

    _instance: EmbeddingModel | None = None

    def __new__(cls) -> EmbeddingModel:
        """Return the singleton instance, creating it if necessary."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        """
        Load the SentenceTransformer model on first instantiation.

        Skips re-initialization on subsequent calls via _initialized guard.
        Logs model name and dimensions for observability.
        """
        if self._initialized:
            return

        model_name = settings.embedding_model_name
        logger.info("embedding_model.loading", model=model_name)

        self._model: SentenceTransformer = SentenceTransformer(model_name)
        self._dimensions: int = settings.embedding_dimensions
        self._initialized = True

        logger.info(
            "embedding_model.loaded",
            model=model_name,
            dimensions=self._dimensions,
        )

    def encode(self, text: str) -> list[float]:
        """
        Encode a text string into a 384-dimension float vector.

        Runs synchronously on CPU. Called from async context via
        asyncio.run_in_executor in agent.py to avoid blocking the event loop.

        Args:
            text: The text to embed. Will be truncated by the model at 256
                word-piece tokens — texts longer than ~400 words are silently
                truncated.

        Returns:
            List of 384 floats representing the text's semantic embedding.

        Raises:
            RuntimeError: If the model is not initialized (should not happen
                        after lifespan startup).
        """
        if not self._initialized:
            raise RuntimeError("EmbeddingModel not initialized — call from lifespan first.")

        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    @property
    def dimensions(self) -> int:
        """Return the embedding dimension count (384 for all-MiniLM-L6-v2)."""
        return self._dimensions