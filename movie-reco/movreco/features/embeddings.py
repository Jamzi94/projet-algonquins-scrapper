"""Calcul des embeddings sémantiques des synopsis (sentence-transformers)."""
from __future__ import annotations

import numpy as np

_MODEL = None


def _model(cfg: dict):
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(cfg["embeddings"]["model"])
    return _MODEL


def embed_texts(texts, cfg: dict) -> np.ndarray:
    """Encode une liste de textes en vecteurs denses normalisés (float32)."""
    model = _model(cfg)
    emb = model.encode(
        list(texts),
        batch_size=cfg["embeddings"].get("batch_size", 64),
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return np.asarray(emb, dtype="float32")
