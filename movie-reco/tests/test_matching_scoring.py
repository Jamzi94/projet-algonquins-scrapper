"""Tests de matching.match_ratings : appariement au seuil, bonus année, rejet.

On simule wikidata.lookup_film via monkeypatch (aucun réseau). Le scoring fuzzy
est réel (rapidfuzz)."""
from __future__ import annotations

import pandas as pd

from movreco.ingest import matching


CFG = {"matching": {"fuzzy_threshold": 86}, "language": "fr"}


def _cand(film: str, label: str, date: str | None = None, imdb: str | None = None) -> dict:
    return {
        "film": f"http://www.wikidata.org/entity/{film}",
        "filmLabel": label,
        "date": date,
        "imdb": imdb,
    }


def test_appariement_au_dessus_du_seuil(monkeypatch):
    def fake_lookup(title, cfg, limit=12):
        return [_cand("Q123", "Inception", "2010-07-16", "tt1375666")]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Inception"], "year": [2010], "rating": [9]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] == "Q123"
    assert out.loc[0, "label"] == "Inception"
    assert out.loc[0, "imdb"] == "tt1375666"
    assert out.loc[0, "match_score"] is not None
    # titre identique -> score fuzzy = 100, > seuil 86
    assert out.loc[0, "match_score"] >= 86


def test_bonus_annee_departage_le_meilleur_candidat(monkeypatch):
    # Deux candidats au même label : le bonus année (+10) doit faire gagner
    # celui dont l'année est proche de l'année utilisateur.
    def fake_lookup(title, cfg, limit=12):
        return [
            _cand("Q_MAUVAIS", "Le Film", "1990-01-01"),
            _cand("Q_BON", "Le Film", "2010-06-01"),
        ]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Le Film"], "year": [2010], "rating": [8]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] == "Q_BON"
    # le score retenu inclut le bonus de +10 (100 + 10)
    assert out.loc[0, "match_score"] == 110.0


def test_bonus_annee_permet_de_franchir_le_seuil(monkeypatch):
    # On choisit un titre dont le score fuzzy de base tombe dans la fenêtre
    # ]seuil-10, seuil[ : rejeté sans bonus, apparié avec le bonus année (+10).
    from rapidfuzz import fuzz

    user_title = "Mission Impossible"
    cand_label = "Mission Impossible Fallout"
    base_score = fuzz.token_sort_ratio(
        matching.normalize_title(user_title), matching.normalize_title(cand_label)
    )
    thr = CFG["matching"]["fuzzy_threshold"]
    # garde-fou : le scénario n'a de sens que si le bonus est décisif
    assert thr - 10 < base_score < thr

    def fake_lookup(title, cfg, limit=12):
        return [_cand("Q_PROCHE", cand_label, "2015-04-04")]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    # sans année : score = base_score < seuil -> rejet
    no_year = matching.match_ratings(
        pd.DataFrame({"title": [user_title], "year": [None], "rating": [7]}), CFG
    )
    assert no_year.loc[0, "qid"] is None

    # avec année proche : score = base_score + 10 >= seuil -> apparié
    with_year = matching.match_ratings(
        pd.DataFrame({"title": [user_title], "year": [2015], "rating": [7]}), CFG
    )
    assert with_year.loc[0, "qid"] == "Q_PROCHE"
    assert with_year.loc[0, "match_score"] == round(base_score + 10, 1)


def test_rejet_sous_le_seuil_donne_qid_none(monkeypatch):
    def fake_lookup(title, cfg, limit=12):
        # candidat totalement différent du titre demandé -> score fuzzy faible
        return [_cand("Q_HORS_SUJET", "Une Histoire Sans Aucun Rapport", "1980-01-01")]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Inception"], "year": [2010], "rating": [9]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] is None
    assert out.loc[0, "label"] is None
    assert out.loc[0, "imdb"] is None
    assert out.loc[0, "match_score"] is None
    # la note et le titre d'origine sont conservés
    assert out.loc[0, "title"] == "Inception"
    assert out.loc[0, "rating"] == 9


def test_aucun_candidat_donne_qid_none(monkeypatch):
    def fake_lookup(title, cfg, limit=12):
        return []

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Film Introuvable"], "year": [2000], "rating": [5]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] is None
    assert out.loc[0, "match_score"] is None
