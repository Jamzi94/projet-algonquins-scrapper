"""Logique métier du service API : chargement de l'état et opérations moteur.

Ce module réutilise STRICTEMENT le pipeline existant (aucune réimplémentation
du scoring). Il charge les artefacts une fois (:func:`load_state`) et expose des
fonctions pures sur l'état : recherche, détail, similarité, recommandation.

numpy/pandas sont importés au niveau module (légers, contrat d'API). Les imports
lourds (faiss via ``recommend.index.build_or_load``) restent dans les fonctions
appelées du pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# État applicatif
# --------------------------------------------------------------------------- #
@dataclass
class AppState:
    """Artefacts chargés une fois au démarrage, partagés entre les requêtes.

    Tout artefact manquant reste à None / DataFrame vide : l'app démarre quand
    même et les endpoints concernés renvoient 503.
    """

    cfg: dict = field(default_factory=dict)
    paths: dict = field(default_factory=dict)
    items: pd.DataFrame | None = None
    emb: np.ndarray | None = None
    emb_ids: list[str] | None = None
    structured: pd.DataFrame | None = None
    model: Any = None
    rated: pd.DataFrame | None = None
    # Index interne qid -> position de ligne dans `items` (recherche O(1)).
    _posmap: dict[str, int] = field(default_factory=dict, repr=False)


def _split_pipe(value: Any) -> list[str]:
    """Découpe une colonne '|'-séparée en liste (vide si NaN/None/'')."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [t for t in str(value).split("|") if t]


def _year_of(row: pd.Series) -> int | None:
    """Extrait l'année depuis la colonne `date` (None si indisponible)."""
    if "date" not in row.index:
        return None
    y = pd.to_datetime(row.get("date"), errors="coerce")
    if pd.isna(y):
        return None
    return int(y.year)


# --------------------------------------------------------------------------- #
# Chargement tolérant des artefacts
# --------------------------------------------------------------------------- #
def load_state(cfg: dict | None = None) -> AppState:
    """Charge l'état applicatif depuis les artefacts du pipeline.

    Tolérant : un artefact absent n'interrompt pas le démarrage (le champ
    correspondant reste à None / vide). Réutilise config.load_config/paths et
    combine.align_embeddings.
    """
    from movreco.config import load_config, paths

    cfg = cfg or load_config()
    P = paths(cfg)
    state = AppState(cfg=cfg, paths=P)

    # items.parquet
    if Path(P["items"]).exists():
        items = pd.read_parquet(P["items"])
        state.items = items
        state._posmap = {q: i for i, q in enumerate(items["qid"].values)}

    # embeddings.npy (+ embeddings_ids.json optionnel) réalignés sur items
    if Path(P["embeddings"]).exists() and state.items is not None:
        import warnings

        from movreco.features.combine import align_embeddings

        emb = np.load(P["embeddings"])
        emb_ids = None
        if Path(P["emb_ids"]).exists():
            emb_ids = json.loads(Path(P["emb_ids"]).read_text())
        # Un catalogue désaligné est une vraie erreur d'exploitation, mais le
        # contrat impose un démarrage tolérant : on dégrade le SEUL état des
        # embeddings (state.emb=None -> endpoints recommend/similar en 503) sans
        # tuer le lifespan. /health et /movies, qui ne dépendent pas des
        # embeddings, restent disponibles. On signale à la requête, pas au boot.
        try:
            state.emb = align_embeddings(emb, emb_ids, state.items)
            state.emb_ids = emb_ids
        except ValueError as exc:
            warnings.warn(
                "Embeddings désynchronisés par rapport au catalogue, ignorés "
                f"au démarrage (relancez 'movreco embed') : {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            state.emb = None
            state.emb_ids = None

    # structured.parquet (indexé par qid)
    if Path(P["structured"]).exists():
        state.structured = pd.read_parquet(P["structured"])

    # models/preference.joblib
    if Path(P["model"]).exists():
        from movreco.model import preference

        state.model = preference.load(P["model"])

    # rated.parquet (qid, rating)
    if Path(P["rated"]).exists():
        state.rated = pd.read_parquet(P["rated"])

    return state


# --------------------------------------------------------------------------- #
# Opérations moteur (pures sur l'état)
# --------------------------------------------------------------------------- #
def search_movies(state: AppState, q: str | None = None, limit: int = 20) -> list[dict]:
    """Recherche insensible à la casse par sous-chaîne sur le label.

    Sans `q`, renvoie les `limit` premiers items du catalogue.
    """
    if state.items is None:
        raise ArtifactMissing("Catalogue indisponible : items.parquet manquant.")
    items = state.items
    if q:
        mask = items["label"].fillna("").str.contains(q, case=False, regex=False)
        sub = items[mask]
    else:
        sub = items
    sub = sub.head(max(limit, 0))
    out: list[dict] = []
    for _, row in sub.iterrows():
        out.append(
            {
                "qid": str(row["qid"]),
                "label": str(row["label"]),
                "year": _year_of(row),
                "genres": _split_pipe(row.get("genres")),
            }
        )
    return out


def get_movie(state: AppState, qid: str) -> dict | None:
    """Détail d'un film (None si qid inconnu)."""
    if state.items is None:
        raise ArtifactMissing("Catalogue indisponible : items.parquet manquant.")
    pos = state._posmap.get(qid)
    if pos is None:
        return None
    row = state.items.iloc[pos]
    return {
        "qid": str(row["qid"]),
        "label": str(row["label"]),
        "year": _year_of(row),
        "genres": _split_pipe(row.get("genres")),
        "directors": _split_pipe(row.get("directors")),
        "countries": _split_pipe(row.get("countries")),
    }


def similar(state: AppState, qid: str, n: int = 10) -> dict | None:
    """Voisins par similarité cosinus des embeddings (exclut le film lui-même).

    Renvoie {"query": {...}, "results": [...]}, ou None si qid inconnu.
    Lève ArtifactMissing si les embeddings ne sont pas chargés.
    """
    if state.items is None:
        raise ArtifactMissing("Catalogue indisponible : items.parquet manquant.")
    if state.emb is None:
        raise ArtifactMissing(
            "Embeddings indisponibles : relancez 'movreco embed'."
        )
    pos = state._posmap.get(qid)
    if pos is None:
        return None

    from movreco.model.taste_vector import cosine_scores

    query_vec = state.emb[pos]
    scores = cosine_scores(query_vec, state.emb)
    # Tri décroissant ; on récupère n+1 pour pouvoir retirer le film lui-même.
    order = np.argsort(-scores)
    qids = state.items["qid"].values
    labels = state.items["label"].values
    results: list[dict] = []
    for i in order:
        i = int(i)
        if i == pos:
            continue
        results.append(
            {"qid": str(qids[i]), "label": str(labels[i]), "score": float(scores[i])}
        )
        if len(results) >= n:
            break

    query_row = state.items.iloc[pos]
    return {
        "query": {"qid": str(query_row["qid"]), "label": str(query_row["label"])},
        "results": results,
    }


def _run_pipeline(
    state: AppState,
    rated_qids: list[str],
    ratings: list[float],
    mode: str,
    n: int,
    exclude: list[str] | None,
) -> tuple[str, list[dict]]:
    """Appelle pipeline.recommend avec repli hybrid -> mvp si modèle absent.

    Renvoie (mode_effectif, results). Profite du cache d'index FAISS persistant.
    """
    from movreco.recommend.pipeline import recommend as run_reco

    # Normalisation défensive : seuls "mvp"/"hybrid" sont des modes réels. Toute
    # autre valeur (la couche HTTP la rejette déjà en 422) est ramenée à "mvp"
    # pour que le `mode` renvoyé reflète TOUJOURS le scoring réellement appliqué
    # (pipeline.recommend applique le scoring mvp pour tout mode != "hybrid").
    effective = mode if mode in ("mvp", "hybrid") else "mvp"
    # Repli : le mode hybride exige modèle ET features structurées.
    if effective == "hybrid" and (state.model is None or state.structured is None):
        effective = "mvp"

    # On surcharge top_n via une copie superficielle de cfg pour ne pas muter
    # l'état partagé. recommend lit cfg["recommend"]["top_n"].
    cfg = dict(state.cfg)
    rc = dict(cfg.get("recommend", {}) or {})
    rc["top_n"] = int(n)
    cfg["recommend"] = rc

    index_path = state.paths.get("faiss")
    result = run_reco(
        state.items,
        state.emb,
        rated_qids,
        np.asarray(ratings, dtype=float),
        mode=effective,
        structured=state.structured,
        model=state.model if effective == "hybrid" else None,
        cfg=cfg,
        exclude=exclude,
        index_path=index_path,
    )
    out = [
        {"qid": str(r["qid"]), "label": str(r["label"]), "score": float(r["score"])}
        for _, r in result.iterrows()
    ]
    return effective, out


def recommend_from_ratings(
    state: AppState,
    ratings: list[dict],
    mode: str = "mvp",
    n: int = 10,
    exclude: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """Recommande à partir de notes fournies par le client (stateless).

    `ratings` : liste de {"qid", "rating"}. On filtre aux qids présents dans le
    catalogue. Lève ArtifactMissing si les embeddings ne sont pas chargés,
    InvalidRequest si aucune note valide.
    """
    if state.emb is None or state.items is None:
        raise ArtifactMissing(
            "Embeddings indisponibles : le moteur ne peut pas recommander."
        )
    if not ratings:
        raise InvalidRequest("Aucune note fournie.")

    valid_qids: list[str] = []
    valid_ratings: list[float] = []
    for r in ratings:
        qid = str(r["qid"])
        if qid in state._posmap:
            valid_qids.append(qid)
            valid_ratings.append(float(r["rating"]))
    if not valid_qids:
        raise InvalidRequest("Aucun film noté ne correspond au catalogue.")

    return _run_pipeline(state, valid_qids, valid_ratings, mode, n, exclude)


def recommend_owner(
    state: AppState, mode: str = "hybrid", n: int = 10
) -> tuple[str, list[dict]]:
    """Recommande à partir des notes persistées du propriétaire (rated.parquet).

    Lève ArtifactMissing si rated ou embeddings absents.
    """
    if state.emb is None or state.items is None:
        raise ArtifactMissing(
            "Embeddings indisponibles : le moteur ne peut pas recommander."
        )
    if state.rated is None:
        raise ArtifactMissing(
            "Aucune note persistée : rated.parquet manquant (lancez 'movreco ingest')."
        )

    rated_qids = state.rated["qid"].tolist()
    ratings = state.rated["rating"].values.astype(float).tolist()
    if not rated_qids:
        raise ArtifactMissing("Aucune note persistée exploitable.")

    return _run_pipeline(state, rated_qids, ratings, mode, n, exclude=None)


# --------------------------------------------------------------------------- #
# Exceptions métier (traduites en HTTPException par la couche app)
# --------------------------------------------------------------------------- #
class ArtifactMissing(RuntimeError):
    """Un artefact requis pour l'opération est absent -> 503."""


class InvalidRequest(ValueError):
    """Requête invalide côté données (ex. aucune note valide) -> 422."""
