"""Apprentissage actif : quels films proposer en priorité à la notation.

En cold-start mono-utilisateur, chaque note coûte cher. On veut donc choisir les
films à faire noter qui apportent le plus d'information : couvrir l'espace des
embeddings le plus largement possible (exploration) plutôt que des doublons
proches de ce qui est déjà connu.

La stratégie est l'échantillonnage du point le plus éloigné (*farthest-point
sampling*) : on retient itérativement le film NON noté dont la distance minimale
à l'ensemble {films déjà notés ∪ films déjà choisis} est maximale. On peut
optionnellement favoriser les films populaires (``lambda_pop``) pour que les
suggestions restent pertinentes/connues de l'utilisateur.

Pur numpy, déterministe (départage par ordre d'indice), aucune dépendance lourde.
"""
from __future__ import annotations

import numpy as np


def _normalize_popularity(popularity, n_items: int) -> np.ndarray | None:
    """Met la popularité à l'échelle [0, 1] (log1p puis division par le max).

    Renvoie ``None`` si ``popularity`` est absent ou de taille incompatible, ce
    qui désactive proprement la pondération. La transformation log amortit les
    écarts énormes de nombre de sitelinks ; les NaN sont traités comme 0.
    """
    if popularity is None:
        return None
    p = np.asarray(popularity, dtype=float)
    if p.shape[0] != n_items:
        return None
    p = np.log1p(np.nan_to_num(p, nan=0.0, posinf=0.0, neginf=0.0))
    pmax = p.max() if p.size else 0.0
    if pmax > 0:
        p = p / pmax
    return p


def suggest_to_rate(
    emb,
    qids,
    rated_qids,
    n: int = 10,
    popularity=None,
    lambda_pop: float = 0.0,
) -> list[str]:
    """Propose au plus ``n`` films NON notés à faire noter en priorité.

    Échantillonnage du point le plus éloigné : à chaque étape on choisit le qid
    non noté qui maximise sa distance (euclidienne) minimale à l'ensemble des
    films de référence (déjà notés ∪ déjà choisis), afin de couvrir au mieux
    l'espace des goûts possibles.

    Paramètres
    ----------
    emb : embeddings des films, aligné ligne par ligne sur ``qids`` (shape
        ``(len(qids), d)``).
    qids : identifiants Wikidata des films, alignés sur ``emb``.
    rated_qids : qids déjà notés par l'utilisateur (exclus des suggestions et
        utilisés comme points de référence initiaux).
    n : nombre maximal de suggestions renvoyées.
    popularity : proxy de popularité aligné sur ``qids`` (ex. nb de sitelinks),
        optionnel. Sert à la pondération et au choix du premier item.
    lambda_pop : poids de la popularité dans le score combiné ``[0, 1]``. À 0
        (défaut) la sélection est purement géométrique (exploration). Plus il est
        grand, plus on favorise des films populaires (pertinence).

    Retour
    ------
    Liste d'au plus ``n`` qids (jamais de notés, jamais de doublon), dans l'ordre
    de sélection. Déterministe : les égalités sont départagées par l'indice le
    plus petit.
    """
    qids = list(qids)
    n_items = len(qids)
    if n_items == 0 or n <= 0:
        return []

    e = np.asarray(emb, dtype="float32")
    if e.ndim == 1:
        # Embeddings scalaires (1 dimension) : une ligne par film.
        if n_items == 1:
            e = e.reshape(1, -1)
        else:
            e = e.reshape(-1, 1)
    if e.shape[0] != n_items:
        raise ValueError(
            "emb et qids doivent être alignés "
            f"(emb: {e.shape[0]} lignes, qids: {n_items})."
        )

    rated_set = set(rated_qids or [])
    # Indices candidats : tous les films non notés, ordre déterministe.
    candidates = [i for i, q in enumerate(qids) if q not in rated_set]
    if not candidates:
        return []

    pop = _normalize_popularity(popularity, n_items)
    use_pop = pop is not None and lambda_pop > 0.0

    # Indices des films notés présents dans le catalogue (points de référence).
    rated_idx = [i for i, q in enumerate(qids) if q in rated_set]

    # Distance min courante de chaque candidat à l'ensemble de référence.
    # np.inf tant qu'aucun point de référence (cas rated vide).
    cand_idx = np.asarray(candidates, dtype=int)
    min_dist = np.full(cand_idx.shape[0], np.inf, dtype=float)

    def _update_min_dist(ref_i: int) -> None:
        """Met à jour ``min_dist`` après ajout du point de référence ``ref_i``."""
        diff = e[cand_idx] - e[ref_i]
        d = np.sqrt(np.einsum("ij,ij->i", diff, diff))
        np.minimum(min_dist, d, out=min_dist)

    for ri in rated_idx:
        _update_min_dist(ri)

    n_target = min(int(n), cand_idx.shape[0])
    chosen: list[str] = []
    # Suit les positions encore disponibles dans cand_idx (masque booléen).
    available = np.ones(cand_idx.shape[0], dtype=bool)

    for step in range(n_target):
        if step == 0 and not rated_idx:
            # Aucun film de référence : on amorce par le plus « central » (le plus
            # proche du centroïde des candidats) ou, si une popularité est fournie
            # et pondérée, par le plus populaire. Ces deux choix donnent un point de
            # départ robuste et utile à noter.
            if use_pop:
                base = pop[cand_idx].astype(float)
            else:
                centroid = e[cand_idx].mean(axis=0)
                diff = e[cand_idx] - centroid
                dist_to_centroid = np.sqrt(np.einsum("ij,ij->i", diff, diff))
                base = -dist_to_centroid  # le plus central = score le plus haut
            base = np.where(available, base, -np.inf)
            local = int(np.argmax(base))
        else:
            # Score = distance min (exploration) + pondération popularité optionnelle.
            score = np.full(cand_idx.shape[0], -np.inf, dtype=float)
            if use_pop:
                # Combine sur les seuls candidats disponibles pour éviter inf*0.
                avail_dist = min_dist[available]
                dmax = avail_dist.max() if avail_dist.size else 0.0
                if dmax > 0:
                    dist_norm = avail_dist / dmax
                else:
                    dist_norm = np.zeros_like(avail_dist)
                combined = (
                    (1.0 - lambda_pop) * dist_norm
                    + lambda_pop * pop[cand_idx][available]
                )
                score[available] = combined
            else:
                score[available] = min_dist[available]
            # argmax renvoie le premier maximum -> départage par indice croissant.
            local = int(np.argmax(score))

        if not available[local]:
            break  # plus rien de disponible (sécurité)

        chosen.append(qids[cand_idx[local]])
        available[local] = False
        # Le film choisi devient un point de référence pour les distances.
        _update_min_dist(int(cand_idx[local]))
        min_dist[local] = -np.inf  # ne plus le re-sélectionner

    return chosen
