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
) -> pd.DataFrame:
    """Renvoie un DataFrame de features indexé par qid.

    `items` doit contenir : qid, genres, directors, countries, date
    (les colonnes genres/directors/countries sont des chaînes séparées par '|').
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

    feats = pd.concat([genres, directors, countries, decade_oh], axis=1).fillna(0).astype("float32")
    feats.index = df["qid"].values
    feats.index.name = "qid"
    return feats
