"""Import de listes de notes externes vers le format movreco (title,year,rating).

Permet de partir de TA vraie liste sans ressaisie : on détecte automatiquement
le format d'export et on le convertit en ``data/input/ratings.csv``.

Formats reconnus :
- **Letterboxd** (export `ratings.csv` : colonnes Name, Year, Rating sur 0.5–5).
- **IMDb** (export `ratings.csv` : colonnes Title, Year, "Your Rating" sur 1–10).
- **Générique** : un CSV possédant déjà title, rating (et year optionnel).

Remarque licences : il s'agit de TES propres notes (ta donnée), utilisées comme
entrée locale. Aucune base IMDb/MovieLens n'est intégrée au produit.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT_COLUMNS = ["title", "year", "rating"]


def _pick(cols_lower: dict[str, str], *candidates: str) -> str | None:
    """Renvoie le nom de colonne réel pour le premier candidat (insensible casse)."""
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    return None


def load_ratings(path: str | Path) -> pd.DataFrame:
    """Charge un export de notes et renvoie un DataFrame (title, year, rating).

    Détecte Letterboxd / IMDb / générique d'après les colonnes. Les notes non
    numériques sont écartées ; ``year`` vaut None si absente.
    """
    df = pd.read_csv(path)
    cols_lower = {c.strip().lower(): c for c in df.columns}

    title_col = _pick(cols_lower, "title", "name", "film", "titre")
    # IMDb : "Your Rating" ; Letterboxd/générique : "Rating".
    rating_col = _pick(cols_lower, "your rating", "rating", "note")
    year_col = _pick(cols_lower, "year", "annee", "année")

    if title_col is None or rating_col is None:
        raise ValueError(
            "Format non reconnu : colonnes title/rating introuvables. "
            f"Colonnes vues : {list(df.columns)}. "
            "Attendu : Letterboxd (Name, Rating), IMDb (Title, 'Your Rating') "
            "ou un CSV title,year,rating."
        )

    out = pd.DataFrame()
    out["title"] = df[title_col].astype(str).str.strip()
    out["year"] = (
        pd.to_numeric(df[year_col], errors="coerce").astype("Int64")
        if year_col is not None
        else pd.Series([pd.NA] * len(df), dtype="Int64")
    )
    out["rating"] = pd.to_numeric(df[rating_col], errors="coerce")

    n_before = len(out)
    out = out[out["title"].astype(bool) & out["rating"].notna()].reset_index(drop=True)
    out.attrs["n_dropped"] = n_before - len(out)
    return out[OUT_COLUMNS]


def import_ratings(source: str | Path, out_path: str | Path) -> pd.DataFrame:
    """Convertit `source` et écrit le CSV movreco à `out_path`. Renvoie le DataFrame."""
    df = load_ratings(source)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df
