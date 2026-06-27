"""Mécanismes de diversification et de dé-biais des recommandations."""
from __future__ import annotations

import numpy as np


def popularity_penalty(scores: np.ndarray, popularity, weight: float) -> np.ndarray:
    """Pénalise les items populaires pour favoriser la découverte.

    `popularity` est un proxy (nombre de sitelinks Wikidata par exemple).
    """
    scores = np.asarray(scores, dtype=float)
    if weight <= 0 or popularity is None:
        return scores
    p = np.asarray(popularity, dtype=float)
    p = np.log1p(np.nan_to_num(p, nan=0.0))
    if p.max() > 0:
        p = p / p.max()
    return scores - weight * p


def mmr(cand_idx, relevance, emb: np.ndarray, k: int, lam: float = 0.7):
    """Maximal Marginal Relevance.

    `cand_idx` : identifiants (ex. positions globales) des candidats.
    `relevance` : score de pertinence aligné sur `cand_idx`.
    `emb` : embeddings des candidats, aligné sur `cand_idx` (emb[i] <-> cand_idx[i]).
    Renvoie (cand_idx sélectionnés, indices locaux sélectionnés).
    """
    relevance = np.asarray(relevance, dtype=float)
    selected_local: list[int] = []
    pool = list(range(len(cand_idx)))
    while pool and len(selected_local) < k:
        best, best_val = None, -1e18
        for i in pool:
            if selected_local:
                diversity = max(float(emb[i] @ emb[j]) for j in selected_local)
            else:
                diversity = 0.0
            val = lam * relevance[i] - (1 - lam) * diversity
            if val > best_val:
                best_val, best = val, i
        selected_local.append(best)
        pool.remove(best)
    chosen = [cand_idx[i] for i in selected_local]
    return chosen, selected_local


def minmax(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.size == 0 or x.max() - x.min() < 1e-9:
        return np.zeros_like(x)
    return (x - x.min()) / (x.max() - x.min())
