"""Appariement de la liste annotée de l'utilisateur aux entités Wikidata."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz

from movreco.ingest import wikidata


def normalize_title(s: str) -> str:
    """Normalise un titre pour la comparaison (minuscules, sans accents ni ponctuation)."""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _qid(uri: str | None) -> str | None:
    return uri.rsplit("/", 1)[-1] if uri else None


def _year(date: str | None) -> str | None:
    return date[:4] if date else None


def match_ratings(ratings: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Pour chaque film noté, trouve la meilleure entité Wikidata.

    `ratings` doit contenir les colonnes : title, year (optionnel), rating.
    Renvoie un DataFrame avec qid, label, imdb, match_score (None si non apparié).
    """
    thr = cfg.get("matching", {}).get("fuzzy_threshold", 86)
    records = []
    for _, row in ratings.iterrows():
        title = row["title"]
        year = row.get("year")
        candidates = wikidata.lookup_film(title, cfg)
        best, best_score = None, -1.0
        norm_title = normalize_title(title)
        for cand in candidates:
            score = fuzz.token_sort_ratio(norm_title, normalize_title(cand.get("filmLabel", "")))
            cand_year = _year(cand.get("date"))
            if year and cand_year:
                try:
                    if abs(int(cand_year) - int(year)) <= 1:
                        score += 10
                except (TypeError, ValueError):
                    pass
            if score > best_score:
                best_score, best = score, cand
        matched = best if (best and best_score >= thr) else None
        records.append(
            {
                "title": title,
                "year": year,
                "rating": row["rating"],
                "qid": _qid(matched.get("film")) if matched else None,
                "label": matched.get("filmLabel") if matched else None,
                "imdb": matched.get("imdb") if matched else None,
                "match_score": round(best_score, 1) if matched else None,
            }
        )
    return pd.DataFrame(records)
