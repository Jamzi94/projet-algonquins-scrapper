"""Vecteur de goût signé et scoring par similarité (cœur du mode MVP)."""
from __future__ import annotations

import numpy as np


def signed_taste_vector(emb_rated: np.ndarray, ratings) -> np.ndarray:
    """Construit un vecteur de goût pondéré par (note - note moyenne).

    Les films aimés (note > moyenne) tirent le vecteur vers eux, les films
    détestés (note < moyenne) le repoussent. Résultat normalisé (float32).
    """
    r = np.asarray(ratings, dtype=float)
    weights = (r - r.mean()).reshape(-1, 1)
    vec = (np.asarray(emb_rated, dtype="float32") * weights).sum(axis=0)
    norm = np.linalg.norm(vec)
    return (vec / norm).astype("float32") if norm else vec.astype("float32")


def cosine_scores(query_vec: np.ndarray, emb: np.ndarray) -> np.ndarray:
    """Similarité cosinus entre un vecteur requête et des embeddings normalisés."""
    return np.asarray(emb, dtype="float32") @ np.asarray(query_vec, dtype="float32")
