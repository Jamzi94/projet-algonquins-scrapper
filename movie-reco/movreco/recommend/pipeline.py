"""Pipeline de recommandation : retrieval -> scoring -> dé-biais -> diversité."""
from __future__ import annotations

import numpy as np
import pandas as pd

from movreco.features.combine import feature_matrix
from movreco.model import preference
from movreco.model.taste_vector import cosine_scores, signed_taste_vector
from movreco.recommend import index as faiss_index
from movreco.recommend.diversity import minmax, mmr, popularity_penalty


def recommend(
    items: pd.DataFrame,
    emb: np.ndarray,
    rated_qids,
    ratings,
    mode: str = "hybrid",
    structured: pd.DataFrame | None = None,
    model=None,
    cfg: dict | None = None,
    exclude=None,
) -> pd.DataFrame:
    """Produit le top-N de recommandations.

    mode="mvp"    : scoring par similarité au vecteur de goût (embeddings seuls).
    mode="hybrid" : scoring par le modèle de préférence supervisé.
    """
    cfg = cfg or {}
    rc = cfg.get("recommend", {})
    top_n = rc.get("top_n", 20)
    n_cand = rc.get("candidates", 400)
    lam = rc.get("mmr_lambda", 0.7)
    pop_w = rc.get("popularity_penalty", 0.15)

    qids = list(items["qid"].values)
    posmap = {q: i for i, q in enumerate(qids)}
    rated_rows = [posmap[q] for q in rated_qids if q in posmap]
    taste = (
        signed_taste_vector(emb[rated_rows], ratings)
        if rated_rows
        else emb.mean(axis=0).astype("float32")
    )

    index = faiss_index.build_index(emb)
    cand_pos, _ = faiss_index.search(index, taste, min(n_cand, len(qids)))

    excluded = set(exclude or []) | set(rated_qids)
    cand_pos = [int(i) for i in cand_pos if qids[int(i)] not in excluded]
    if not cand_pos:
        return pd.DataFrame(columns=["qid", "label", "score"])
    cand_qids = [qids[i] for i in cand_pos]

    if mode == "hybrid" and model is not None and structured is not None:
        X = feature_matrix(cand_qids, items, emb, structured)
        scores = preference.predict(model, X)
    else:
        scores = cosine_scores(taste, emb[cand_pos])
    scores = np.asarray(scores, dtype=float)

    popularity = items.iloc[cand_pos]["popularity"].values if "popularity" in items.columns else None
    scores = popularity_penalty(scores, popularity, pop_w)

    sub_emb = emb[cand_pos]
    chosen_pos, chosen_local = mmr(cand_pos, minmax(scores), sub_emb, top_n, lam)

    result = items.iloc[chosen_pos][["qid", "label"]].copy()
    result["score"] = [float(scores[i]) for i in chosen_local]
    return result.reset_index(drop=True)
