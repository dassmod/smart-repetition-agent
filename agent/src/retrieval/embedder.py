"""
Embedder - turns text into vectors using a small local static-embedding model.

No API key, no torch, runs offline. Model weights download once from
Hugging Face on first use, then are cached under ~/.cache/huggingface.
"""

import numpy as np
from model2vec import StaticModel

MODEL_NAME = "minishlab/potion-base-8M"

_model: StaticModel | None = None


def _get_model() -> StaticModel:
    """Load the embedding model once, reuse across calls."""
    global _model
    if _model is None:
        _model = StaticModel.from_pretrained(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Turn a list of strings into a 2D array of embeddings, one row per string.

    Returns:
        Array of shape (len(texts), embedding_dim)
    """
    model = _get_model()
    return model.encode(texts)


def embed_query(text: str) -> np.ndarray:
    """Embed a single query string. Returns a 1D vector."""
    return embed_texts([text])[0]
