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


def novelty_scores(sub_emb: np.ndarray, taste: np.ndarray) -> np.ndarray:
    """Nouveauté de chaque embedding vis-à-vis du vecteur de goût.

    Définie comme ``1 - cosinus(sub_emb, taste)`` : un item très proche du goût
    (cosinus ~1) a une nouveauté ~0, un item éloigné (cosinus ~-1) une nouveauté
    ~2. ``sub_emb`` doit être aligné ligne par ligne sur les candidats. Aucune
    hypothèse de normalisation n'est faite : le cosinus est calculé explicitement.
    """
    e = np.asarray(sub_emb, dtype=float)
    t = np.asarray(taste, dtype=float)
    if e.size == 0:
        return np.zeros(0, dtype=float)
    if e.ndim == 1:
        e = e.reshape(1, -1)
    en = np.linalg.norm(e, axis=1)
    tn = np.linalg.norm(t)
    denom = en * tn
    cos = np.zeros(e.shape[0], dtype=float)
    nonzero = denom > 1e-12
    cos[nonzero] = (e[nonzero] @ t) / denom[nonzero]
    return 1.0 - cos


def serendipity_picks(
    cand_idx,
    relevance,
    novelty,
    n_pick: int,
    already_local=None,
):
    """Réserve des emplacements à des candidats pertinents MAIS éloignés du goût.

    Sélectionne au plus ``n_pick`` candidats qui (a) restent pertinents — score de
    pertinence strictement au-dessus de la médiane des candidats considérés — et
    (b) maximisent la nouveauté (faible cosinus au goût, cf. :func:`novelty_scores`).
    Le tri est déterministe (nouveauté décroissante, puis pertinence décroissante,
    puis indice local croissant pour départager).

    Paramètres
    ----------
    cand_idx : positions globales des candidats (aligné sur ``relevance``/``novelty``).
    relevance : pertinence par candidat (échelle quelconque, p.ex. [0,1]).
    novelty : nouveauté par candidat (cf. ``novelty_scores``).
    n_pick : nombre maximal d'emplacements sérendipité à pourvoir.
    already_local : indices locaux déjà retenus ailleurs (exclus de la sélection).

    Renvoie ``(chosen_global, chosen_local)`` : positions globales et indices locaux
    des candidats retenus, dans l'ordre de sélection.
    """
    relevance = np.asarray(relevance, dtype=float)
    novelty = np.asarray(novelty, dtype=float)
    already = set(int(i) for i in (already_local or []))
    if n_pick <= 0 or len(cand_idx) == 0:
        return [], []

    eligible = [i for i in range(len(cand_idx)) if i not in already]
    if not eligible:
        return [], []

    # Garde-fou de pertinence : on ne retient que les candidats au-dessus de la
    # médiane de pertinence (parmi les éligibles) pour éviter de recommander du
    # bruit sous prétexte de nouveauté.
    rel_eligible = relevance[eligible]
    threshold = float(np.median(rel_eligible))
    relevant = [i for i in eligible if relevance[i] >= threshold]
    if not relevant:
        relevant = eligible

    relevant.sort(key=lambda i: (-novelty[i], -relevance[i], i))
    picked_local = relevant[: int(n_pick)]
    chosen_global = [cand_idx[i] for i in picked_local]
    return chosen_global, picked_local
