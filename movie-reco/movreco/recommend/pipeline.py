"""Pipeline de recommandation : retrieval -> scoring -> dé-biais -> diversité."""
from __future__ import annotations

import numpy as np
import pandas as pd

from movreco.features.combine import feature_matrix
from movreco.model import preference
from movreco.model.taste_vector import cosine_scores, signed_taste_vector
from movreco.recommend import index as faiss_index
from movreco.recommend.diversity import (
    minmax,
    mmr,
    novelty_scores,
    popularity_penalty,
    serendipity_picks,
)


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
    index_path=None,
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
    # Sérendipité : fraction [0,1] du top-N réservée à des items pertinents mais
    # éloignés du goût. 0.0 (défaut) -> comportement strictement inchangé.
    serendipity = float(rc.get("serendipity", 0.0) or 0.0)
    serendipity = min(max(serendipity, 0.0), 1.0)

    qids = list(items["qid"].values)
    posmap = {q: i for i, q in enumerate(qids)}
    rated_rows = [posmap[q] for q in rated_qids if q in posmap]
    if rated_rows:
        taste = signed_taste_vector(emb[rated_rows], ratings)
    else:
        # Aucune note appariée : repli sur la moyenne des embeddings, normalisée
        # pour rester cohérent avec un index à produit scalaire (cosinus).
        mean = emb.mean(axis=0)
        mnorm = np.linalg.norm(mean)
        taste = (mean / mnorm if mnorm else mean).astype("float32")

    if index_path is not None:
        index = faiss_index.build_or_load(emb, index_path)
    else:
        index = faiss_index.build_index(emb)
    # En mode sérendipité, on a besoin d'un vivier de candidats assez large pour
    # contenir des films pertinents MAIS éloignés du goût (au-delà du strict
    # voisinage du vecteur de goût). On augmente donc le nombre de candidats
    # récupérés sans jamais réduire le comportement par défaut.
    k_search = min(n_cand, len(qids))
    if serendipity > 0.0:
        k_search = min(max(n_cand, 4 * top_n), len(qids))
    cand_pos, _ = faiss_index.search(index, taste, k_search)

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

    # L'échelle du score brut diffère selon le mode (cosinus ~[-1,1] vs note
    # prédite ~0-10). On normalise en [0,1] AVANT la pénalité de popularité afin
    # que celle-ci reste effective dans les deux modes, puis on s'en sert comme
    # pertinence pour le MMR. Le score brut est conservé pour l'affichage.
    popularity = items.iloc[cand_pos]["popularity"].values if "popularity" in items.columns else None
    relevance = popularity_penalty(minmax(scores), popularity, pop_w)

    sub_emb = emb[cand_pos]
    rel_norm = minmax(relevance)

    n_ser = int(round(top_n * serendipity)) if serendipity > 0.0 else 0
    # On ne réserve jamais TOUT le top-N à la sérendipité : on garde au moins une
    # place pour la sélection MMR pertinente.
    n_ser = min(n_ser, max(top_n - 1, 0))

    if n_ser <= 0:
        chosen_pos, chosen_local = mmr(cand_pos, rel_norm, sub_emb, top_n, lam)
    else:
        # 1) Sélection MMR habituelle pour la majeure partie du top-N.
        n_mmr = top_n - n_ser
        mmr_pos, mmr_local = mmr(cand_pos, rel_norm, sub_emb, n_mmr, lam)

        # 2) Emplacements sérendipité : items pertinents (au-dessus de la médiane
        # de pertinence) mais à forte nouveauté (faible cosinus au goût). On
        # exclut ceux déjà retenus par le MMR pour éviter les doublons.
        novelty = novelty_scores(sub_emb, taste)
        ser_pos, ser_local = serendipity_picks(
            cand_pos, relevance, novelty, n_ser, already_local=mmr_local
        )

        chosen_pos = list(mmr_pos) + list(ser_pos)
        chosen_local = list(mmr_local) + list(ser_local)

        # 3) Si la sérendipité n'a pas pu pourvoir tous ses emplacements (vivier
        # trop petit), on complète avec la suite du classement MMR pour garantir
        # une longueur finale de top_n sans doublon.
        if len(chosen_local) < top_n:
            taken = set(chosen_local)
            extra_pos, extra_local = mmr(cand_pos, rel_norm, sub_emb, top_n, lam)
            for gp, lp in zip(extra_pos, extra_local):
                if lp in taken:
                    continue
                chosen_pos.append(gp)
                chosen_local.append(lp)
                taken.add(lp)
                if len(chosen_local) >= top_n:
                    break

    result = items.iloc[chosen_pos][["qid", "label"]].copy()
    result["score"] = [float(scores[i]) for i in chosen_local]
    return result.reset_index(drop=True)
