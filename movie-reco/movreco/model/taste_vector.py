"""Vecteur de goût signé et scoring par similarité (cœur du mode MVP)."""
from __future__ import annotations

import numpy as np


def signed_taste_vector(emb_rated: np.ndarray, ratings) -> np.ndarray:
    """Construit un vecteur de goût pondéré par (note - note moyenne).

    Les films aimés (note > moyenne) tirent le vecteur vers eux, les films
    détestés (note < moyenne) le repoussent. Résultat normalisé (float32).

    Si la pondération s'annule (notes toutes égales / une seule note) et que
    `emb_rated` n'est pas vide, repli sur la moyenne normalisée des embeddings
    notés plutôt que de renvoyer un vecteur nul. Si `emb_rated` est vide,
    renvoie un vecteur de zéros (le pipeline gère ce cas).
    """
    e = np.asarray(emb_rated, dtype="float32")
    r = np.asarray(ratings, dtype=float)
    weights = (r - r.mean()).reshape(-1, 1)
    vec = (e * weights).sum(axis=0)
    norm = np.linalg.norm(vec)
    if norm:
        return (vec / norm).astype("float32")
    if e.shape[0]:
        mean = e.mean(axis=0)
        mnorm = np.linalg.norm(mean)
        if mnorm:
            return (mean / mnorm).astype("float32")
    return vec.astype("float32")


def cosine_scores(query_vec: np.ndarray, emb: np.ndarray) -> np.ndarray:
    """Similarité cosinus entre un vecteur requête et des embeddings normalisés."""
    return np.asarray(emb, dtype="float32") @ np.asarray(query_vec, dtype="float32")
