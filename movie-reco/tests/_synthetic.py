"""Catalogue synthétique pour les tests d'intégration (aucun réseau, aucun modèle).

Génère un faux catalogue de films STRUCTURÉ par genres : chaque genre possède un
centroïde aléatoire (graine fixe), et chaque film est ce centroïde plus un bruit
faible. Les embeddings sont normalisés (cohérents avec un index à produit scalaire
= cosinus). Cela permet de valider la PERTINENCE des recommandations sans
sentence-transformers : un utilisateur qui aime un genre doit recevoir des films
du même genre.

Tout est écrit aux emplacements canoniques de :func:`movreco.config.paths`, et un
``cfg`` est renvoyé pour alimenter ``create_app(cfg)``.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_synthetic_catalog(
    data_dir,
    models_dir=None,
    n_genres: int = 4,
    per_genre: int = 15,
    dim: int = 16,
    seed: int = 0,
):
    """Construit un catalogue synthétique sur disque et renvoie ses métadonnées.

    Écrit, sous ``<data_dir>/processed`` :
      - items.parquet         (qid, label, date, popularity, genres, directors, countries)
      - embeddings.npy        (matrice float32 normalisée, alignée sur items["qid"])
      - embeddings_ids.json   (liste des qid, alignée sur embeddings.npy)
      - structured.parquet    (features structurées via build_structured_features)
      - rated.parquet         (notes du propriétaire : aime fortement le genre 0)

    Paramètres
    ----------
    data_dir : chemin du dossier de données (souvent ``tmp_path``).
    models_dir : dossier des modèles (défaut : ``<data_dir>/models``).
    n_genres, per_genre, dim, seed : taille et reproductibilité du catalogue.

    Renvoie
    -------
    dict avec les clés :
      - "cfg"              : configuration prête pour ``create_app(cfg)``
      - "items"            : DataFrame du catalogue
      - "emb"              : np.ndarray des embeddings (alignés sur items)
      - "genre_to_qids"    : mapping nom de genre -> liste de qid
      - "qid_to_genre"     : mapping qid -> nom de genre
      - "genre_names"      : liste ordonnée des noms de genres
      - "owner_genre"      : nom du genre aimé par le propriétaire (genre 0)
      - "owner_qids"       : qids notés par le propriétaire
      - "data_dir" / "models_dir" : chemins effectifs (Path)
    """
    from movreco.config import load_config
    from movreco.features.structured import build_structured_features

    data_dir = Path(data_dir)
    models_dir = Path(models_dir) if models_dir is not None else (data_dir / "models")
    processed = data_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)

    # Un centroïde normalisé par genre : les genres sont des directions distinctes
    # de l'espace d'embedding.
    centroids = rng.normal(size=(n_genres, dim))
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)

    genre_names = [f"Genre {g}" for g in range(n_genres)]
    qids: list[str] = []
    labels: list[str] = []
    genres: list[str] = []
    directors: list[str] = []
    countries: list[str] = []
    dates: list[str] = []
    popularity: list[float] = []
    vectors: list[np.ndarray] = []

    genre_to_qids: dict[str, list[str]] = {name: [] for name in genre_names}
    qid_to_genre: dict[str, str] = {}

    idx = 0
    for g in range(n_genres):
        gname = genre_names[g]
        for i in range(per_genre):
            idx += 1
            qid = f"Qsynth{idx:03d}"
            # film = centroïde du genre + bruit faible, puis normalisation.
            v = centroids[g] + 0.05 * rng.normal(size=dim)
            norm = np.linalg.norm(v)
            v = (v / norm) if norm else v

            qids.append(qid)
            labels.append(f"{gname} film {i}")
            genres.append(gname)
            directors.append(f"Réalisateur {g}")
            countries.append(f"Pays {g % 3}")
            # Dates variées et déterministes (décennies multiples).
            year = 1980 + (idx % 40)
            dates.append(f"{year}-01-01")
            popularity.append(float(rng.integers(1, 100)))
            vectors.append(v.astype("float32"))

            genre_to_qids[gname].append(qid)
            qid_to_genre[qid] = gname

    items = pd.DataFrame(
        {
            "qid": qids,
            "label": labels,
            "date": dates,
            "popularity": popularity,
            "genres": genres,
            "directors": directors,
            "countries": countries,
        }
    )
    emb = np.asarray(vectors, dtype="float32")

    # --- Écriture des artefacts ------------------------------------------- #
    items.to_parquet(processed / "items.parquet")
    np.save(processed / "embeddings.npy", emb)
    (processed / "embeddings_ids.json").write_text(
        json.dumps(list(items["qid"].values)), encoding="utf-8"
    )

    structured = build_structured_features(items)
    structured.to_parquet(processed / "structured.parquet")

    # Propriétaire : aime fortement le genre 0, n'aime pas le genre 1.
    owner_genre = genre_names[0]
    liked = genre_to_qids[owner_genre][:3]
    disliked = genre_to_qids[genre_names[1]][:2] if n_genres > 1 else []
    owner_qids = liked + disliked
    rated = pd.DataFrame(
        {
            "qid": owner_qids,
            "rating": [5.0] * len(liked) + [1.0] * len(disliked),
        }
    )
    rated.to_parquet(processed / "rated.parquet")

    # --- Construction du cfg pour create_app ------------------------------ #
    cfg = load_config()
    cfg["paths"] = {"data_dir": str(data_dir), "models_dir": str(models_dir)}
    # Catalogue petit : on borne les candidats pour rester rapide et déterministe.
    rc = dict(cfg.get("recommend", {}) or {})
    rc.setdefault("top_n", 10)
    rc["candidates"] = min(rc.get("candidates", 400), n_genres * per_genre)
    cfg["recommend"] = rc

    return {
        "cfg": cfg,
        "items": items,
        "emb": emb,
        "genre_to_qids": genre_to_qids,
        "qid_to_genre": qid_to_genre,
        "genre_names": genre_names,
        "owner_genre": owner_genre,
        "owner_qids": owner_qids,
        "data_dir": data_dir,
        "models_dir": models_dir,
    }
