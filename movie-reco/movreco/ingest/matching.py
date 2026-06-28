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


def _candidate_titles(cand: dict) -> list[str]:
    """Liste des titres candidats à comparer : filmLabel, title (P1476), altLabels.

    Les champs ``title`` et ``altLabels`` (renvoyés par wikidata.lookup_film) sont
    OPTIONNELS : leur absence reproduit le comportement historique (seul filmLabel
    était comparé). Les agrégats GROUP_CONCAT sont éclatés sur le séparateur '|'.
    """
    titles: list[str] = []
    label = cand.get("filmLabel")
    if label:
        titles.append(label)
    for key in ("title", "altLabels"):
        raw = cand.get(key)
        if not raw:
            continue
        for part in str(raw).split("|"):
            part = part.strip()
            if part:
                titles.append(part)
    return titles


def best_title_score(norm_user_title: str, cand: dict) -> float:
    """Meilleur score fuzzy entre le titre utilisateur (déjà normalisé) et le candidat.

    Compare ``norm_user_title`` à chacun des titres du candidat (filmLabel, titre
    officiel P1476, chaque altLabel), chacun normalisé via :func:`normalize_title`,
    et renvoie le score maximal (0.0 si aucun titre exploitable).
    """
    best = 0.0
    for title in _candidate_titles(cand):
        score = fuzz.token_sort_ratio(norm_user_title, normalize_title(title))
        if score > best:
            best = score
    return float(best)


def _qid(uri: str | None) -> str | None:
    return uri.rsplit("/", 1)[-1] if uri else None


def _year(date: str | None) -> str | None:
    return date[:4] if date else None


def _as_int_year(value) -> int | None:
    """Convertit une année en entier exploitable, ou None (gère NaN/None/non-numérique)."""
    if value is None:
        return None
    try:
        if pd.isna(value):  # NaN flottant, NaT, etc.
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None


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
        user_year = _as_int_year(year)
        candidates = wikidata.lookup_film(title, cfg)
        best, best_score = None, -1.0
        norm_title = normalize_title(title)
        for cand in candidates:
            score = best_title_score(norm_title, cand)
            cand_year = _as_int_year(_year(cand.get("date")))
            if user_year is not None and cand_year is not None:
                if abs(cand_year - user_year) <= 1:
                    score += 10
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
