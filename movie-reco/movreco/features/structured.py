"""Construction des features structurées à partir des métadonnées Wikidata."""
from __future__ import annotations

from collections import Counter

import pandas as pd


def _topk_multihot(series_of_lists: pd.Series, top_k: int, prefix: str) -> pd.DataFrame:
    counter: Counter = Counter()
    for lst in series_of_lists:
        for value in lst:
            if value:
                counter[value] += 1
    keep = [value for value, _ in counter.most_common(top_k)]
    # Ordre déterministe : fréquence décroissante puis valeur alphabétique.
    keep.sort(key=lambda value: (-counter[value], value))
    cols = {
        f"{prefix}__{value}": series_of_lists.apply(lambda lst, v=value: 1 if v in lst else 0)
        for value in keep
    }
    return pd.DataFrame(cols, index=series_of_lists.index)


def build_structured_features(
    items: pd.DataFrame,
    top_genres: int = 60,
    top_directors: int = 200,
    top_countries: int = 40,
    top_actors: int = 300,
    top_keywords: int = 100,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Renvoie un DataFrame de features indexé par qid.

    `items` doit contenir : qid, genres, directors, countries, date
    (les colonnes genres/directors/countries sont des chaînes séparées par '|').

    Colonnes optionnelles (ignorées proprement si absentes, rétro-compatible) :
    - "cast" : acteurs ('|'-séparés) -> multi-hot préfixe "actor__"
    - "keywords" : sujets principaux ('|'-séparés) -> multi-hot préfixe "kw__"
    - "languages" : langues d'origine ('|'-séparées) -> multi-hot préfixe "lang__"
    - "duration" : durée en minutes -> feature numérique "duration_min"
      (float, 0.0 si absente ou non numérique).

    Si une de ces colonnes est absente, elle n'introduit aucune colonne : pour un
    catalogue sans ces métadonnées, le résultat est strictement identique au
    comportement historique (genres/directors/countries/décennie uniquement).

    Si `columns` est fourni, la sortie est réindexée exactement sur ces colonnes
    (colonnes absentes réintroduites à 0, colonnes en trop ignorées), ce qui
    garantit un schéma identique entre entraînement et prédiction.
    """
    df = items.copy().reset_index(drop=True)

    def split(col: str) -> pd.Series:
        return df[col].fillna("").apply(lambda s: [t for t in str(s).split("|") if t])

    genres = _topk_multihot(split("genres"), top_genres, "genre")
    directors = _topk_multihot(split("directors"), top_directors, "dir")
    countries = _topk_multihot(split("countries"), top_countries, "country")

    year = pd.to_datetime(df["date"], errors="coerce").dt.year
    decade = ((year // 10) * 10).fillna(0).astype(int)
    decade_oh = pd.get_dummies(decade, prefix="decade")

    blocks = [genres, directors, countries, decade_oh]

    # Colonnes enrichies : ajoutées seulement si présentes (rétro-compatibilité).
    if "cast" in df.columns:
        blocks.append(_topk_multihot(split("cast"), top_actors, "actor"))
    if "keywords" in df.columns:
        blocks.append(_topk_multihot(split("keywords"), top_keywords, "kw"))
    if "languages" in df.columns:
        # Pas de troncature : les langues d'origine sont en nombre limité.
        blocks.append(_topk_multihot(split("languages"), top_k=10_000, prefix="lang"))
    if "duration" in df.columns:
        duration_min = (
            pd.to_numeric(df["duration"], errors="coerce")
            .fillna(0.0)
            .astype("float32")
        )
        duration_df = pd.DataFrame({"duration_min": duration_min}, index=df.index)
        blocks.append(duration_df)

    feats = pd.concat(blocks, axis=1).fillna(0).astype("float32")
    feats.index = df["qid"].values
    feats.index.name = "qid"
    if columns is not None:
        feats = feats.reindex(columns=columns, fill_value=0).astype("float32")
    return feats
