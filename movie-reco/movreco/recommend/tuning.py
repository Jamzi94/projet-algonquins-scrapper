"""Outil de tuning hors-ligne des hyperparamètres de recommandation.

Mesure la qualité d'un jeu d'hyperparamètres ``recommend`` (MMR, sérendipité,
pénalité de popularité, nombre de candidats) par validation *holdout* sur les
films AIMÉS du propriétaire :

1. On cache une fraction des films aimés (notes strictement au-dessus de la
   médiane des notes).
2. On lance :func:`movreco.recommend.pipeline.recommend` sur les notes RESTANTES,
   les films cachés étant retirés du jeu de notes (donc inconnus du vecteur de
   goût) MAIS toujours présents dans le catalogue, donc éligibles comme
   candidats à retrouver.
3. On mesure ``recall@k`` (part des films cachés retrouvés dans le top-k) et
   ``ndcg@k`` (qualité du classement de réapparition).

Tout est déterministe (graine fixe) et purement hors-ligne ; les imports lourds
(``faiss`` via le pipeline) restent dans les fonctions, conformément aux
conventions du projet.
"""
from __future__ import annotations

import copy

import numpy as np


def _holdout_split(rated_qids, ratings, holdout_frac: float, seed: int):
    """Sépare les films AIMÉS en (train, holdout) de façon déterministe.

    Les films « aimés » sont ceux dont la note est AU-DESSUS de la médiane des
    notes (``>= médiane``) : on capte ainsi la moitié haute des préférences même
    lorsque les meilleures notes sont à égalité (cas fréquent : plusieurs films
    notés au maximum). On en cache une fraction ``holdout_frac`` (au moins un
    film dès qu'il y a assez de matière), tirée avec une graine fixe pour la
    reproductibilité.

    Renvoie ``(train_qids, train_ratings, holdout_qids)`` où ``train_*`` sont des
    listes alignées (qids + notes correspondantes) et ``holdout_qids`` la liste
    des qids cachés. Renvoie des structures vides si l'échantillon est trop petit
    pour produire à la fois un holdout non vide et un train non vide.
    """
    qids = list(rated_qids)
    r = np.asarray(list(ratings), dtype=float)
    n = len(qids)
    if n != len(r) or n < 2:
        return [], np.asarray([], dtype=float), []

    # Films aimés : note au-dessus de la médiane (``>=``). Lorsque toutes les
    # notes sont égales, tous les films sont « aimés » : on garde quand même un
    # film en TRAIN (cf. plafond du holdout plus bas) pour que le vecteur de goût
    # ne soit pas vide.
    median = float(np.median(r))
    liked_idx = [i for i in range(n) if r[i] >= median]
    if len(liked_idx) < 2:
        return [], np.asarray([], dtype=float), []

    # Tirage déterministe d'une fraction des films aimés à cacher.
    rng = np.random.default_rng(seed)
    liked_sorted = sorted(liked_idx, key=lambda i: qids[i])  # ordre stable
    perm = rng.permutation(len(liked_sorted))
    ordered = [liked_sorted[p] for p in perm]

    n_holdout = int(round(len(ordered) * float(holdout_frac)))
    n_holdout = max(1, min(n_holdout, len(ordered) - 1))  # train ET holdout non vides

    holdout_set = set(ordered[:n_holdout])
    holdout_qids = [qids[i] for i in sorted(holdout_set)]
    train_qids = [qids[i] for i in range(n) if i not in holdout_set]
    train_ratings = np.asarray(
        [r[i] for i in range(n) if i not in holdout_set], dtype=float
    )
    return train_qids, train_ratings, holdout_qids


def evaluate_recall(
    items,
    emb,
    structured,
    rated_qids,
    ratings,
    cfg: dict,
    k: int = 10,
    holdout_frac: float = 0.3,
    seed: int = 0,
) -> dict:
    """Évalue un jeu d'hyperparamètres par holdout sur les films aimés.

    Cache une fraction (``holdout_frac``) des films aimés (note > médiane), lance
    le pipeline de recommandation sur les notes restantes en EXCLUANT les films
    cachés du jeu de notes (mais en les laissant candidats dans le catalogue),
    puis mesure :

    - ``recall_at_k`` : fraction des films cachés présents dans le top-k.
    - ``ndcg_at_k``   : NDCG@k où les films cachés valent 1 et les autres 0
      (qualité du classement de réapparition).

    Paramètres
    ----------
    items : DataFrame du catalogue (colonnes ``qid``, ``label``, ...).
    emb : embeddings alignés sur les lignes de ``items``.
    structured : features structurées indexées par qid (peut être ``None``).
    rated_qids, ratings : notes du propriétaire (listes/array alignés).
    cfg : configuration ; ``cfg["recommend"]`` porte les hyperparamètres.
    k : taille du top considéré pour recall@k / ndcg@k.
    holdout_frac : fraction des films aimés à cacher.
    seed : graine du tirage du holdout (déterminisme).

    Renvoie
    -------
    dict ``{"recall_at_k", "ndcg_at_k", "n_holdout"}``. Si l'échantillon est trop
    petit pour un holdout valide, renvoie ``recall_at_k=nan``, ``ndcg_at_k=nan``
    et ``n_holdout=0``.
    """
    # Imports lourds dans la fonction (faiss est tiré par le pipeline).
    from movreco.model.evaluate import ndcg_at_k
    from movreco.recommend.pipeline import recommend as run_reco

    train_qids, train_ratings, holdout_qids = _holdout_split(
        rated_qids, ratings, holdout_frac, seed
    )
    n_holdout = len(holdout_qids)
    if n_holdout == 0 or not train_qids:
        return {"recall_at_k": float("nan"), "ndcg_at_k": float("nan"), "n_holdout": 0}

    # On vise un top-N au moins égal à k pour pouvoir mesurer recall@k sans être
    # bridé par un top_n de config plus petit. On copie cfg["recommend"] pour ne
    # jamais muter la configuration de l'appelant.
    rc = dict((cfg or {}).get("recommend", {}) or {})
    rc["top_n"] = max(int(rc.get("top_n", 0) or 0), int(k))
    eval_cfg = dict(cfg or {})
    eval_cfg["recommend"] = rc

    # Mode "mvp" : scoring par similarité au vecteur de goût (déterministe,
    # sans modèle supervisé à réentraîner pour chaque combinaison testée). Les
    # films cachés ne sont PAS exclus du catalogue : ils restent candidats.
    result = run_reco(
        items,
        emb,
        train_qids,
        np.asarray(train_ratings, dtype=float),
        mode="mvp",
        structured=structured,
        model=None,
        cfg=eval_cfg,
        exclude=None,
        index_path=None,
    )

    if result is None or len(result) == 0:
        return {"recall_at_k": 0.0, "ndcg_at_k": 0.0, "n_holdout": n_holdout}

    top = list(result["qid"].values[:k])
    holdout_set = set(holdout_qids)

    found = sum(1 for q in top if q in holdout_set)
    recall = found / float(n_holdout) if n_holdout else float("nan")

    # NDCG@k de réapparition : pertinence binaire (1 si film caché), scores =
    # ordre du top (le 1er a le meilleur score). Les films retrouvés haut dans le
    # classement comptent davantage.
    y_true = [1.0 if q in holdout_set else 0.0 for q in top]
    y_score = list(range(len(top), 0, -1))  # décroissant : préserve l'ordre du top
    ndcg = ndcg_at_k(y_true, y_score, k) if top else 0.0

    return {
        "recall_at_k": float(recall),
        "ndcg_at_k": float(ndcg),
        "n_holdout": int(n_holdout),
    }


def sweep(
    items,
    emb,
    structured,
    rated_qids,
    ratings,
    grid: dict,
    cfg: dict,
    k: int = 10,
    holdout_frac: float = 0.3,
) -> list[dict]:
    """Balaie une grille d'hyperparamètres et classe par recall@k décroissant.

    ``grid`` associe un nom de paramètre à une liste de valeurs à tester, parmi
    ``mmr_lambda``, ``serendipity``, ``popularity_penalty`` et ``candidates``.
    Le produit cartésien des valeurs est évalué ; chaque combinaison est
    appliquée dans une COPIE de ``cfg["recommend"]`` puis passée à
    :func:`evaluate_recall`.

    Renvoie
    -------
    liste de dicts (un par combinaison) triée par ``recall_at_k`` décroissant
    (puis ``ndcg_at_k`` décroissant pour départager). Chaque dict contient :
    ``{"params", "recall_at_k", "ndcg_at_k", "n_holdout"}`` où ``params`` est le
    dict des valeurs appliquées pour cette combinaison.
    """
    import itertools

    grid = grid or {}
    # On ne retient que les clés connues, dans un ordre stable, pour un balayage
    # déterministe et reproductible.
    known = ["mmr_lambda", "serendipity", "popularity_penalty", "candidates"]
    keys = [key for key in known if key in grid and grid[key]]
    value_lists = [list(grid[key]) for key in keys]

    results: list[dict] = []
    combos = list(itertools.product(*value_lists)) if keys else [()]
    for combo in combos:
        params = {key: val for key, val in zip(keys, combo)}

        # Copie profonde de cfg pour isoler chaque combinaison ; on n'altère
        # jamais la config de l'appelant.
        combo_cfg = copy.deepcopy(cfg or {})
        rc = dict(combo_cfg.get("recommend", {}) or {})
        rc.update(params)
        combo_cfg["recommend"] = rc

        metrics = evaluate_recall(
            items,
            emb,
            structured,
            rated_qids,
            ratings,
            combo_cfg,
            k=k,
            holdout_frac=holdout_frac,
        )
        results.append({"params": params, **metrics})

    # Tri par recall@k décroissant, ndcg@k décroissant en départage. Les nan
    # sont renvoyés en fin de classement (traités comme -inf).
    def _key(row):
        rec = row.get("recall_at_k", float("nan"))
        nd = row.get("ndcg_at_k", float("nan"))
        rec = rec if rec == rec else float("-inf")
        nd = nd if nd == nd else float("-inf")
        return (rec, nd)

    results.sort(key=_key, reverse=True)
    return results
