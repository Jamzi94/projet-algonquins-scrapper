"""Tests de l'appariement P1476 / altLabels (Équipe 1).

``matching.match_ratings`` ne doit plus comparer le titre utilisateur au seul
``filmLabel`` : le meilleur score parmi {``filmLabel``, ``title`` (titre officiel
P1476), chaque ``altLabel``} doit être retenu. On simule ``wikidata.lookup_film``
par monkeypatch (aucun réseau). Le scoring fuzzy reste réel (rapidfuzz).

On vérifie :
  - un candidat dont le ``filmLabel`` NE matche PAS mais dont le ``title`` (P1476)
    matche -> appariement réussi ;
  - idem via un ``altLabel`` (champ '|'-séparé) ;
  - rétro-compatibilité stricte : sans ``title``/``altLabels`` le comportement est
    inchangé (seul ``filmLabel`` est comparé) ;
  - le helper ``best_title_score`` prend bien le max et tolère les champs absents.
"""
from __future__ import annotations

import pandas as pd

from movreco.ingest import matching


CFG = {"matching": {"fuzzy_threshold": 86}, "language": "fr"}


def test_title_p1476_permet_l_appariement(monkeypatch):
    # Le filmLabel est un identifiant brut (ne matche pas), mais le titre officiel
    # P1476 correspond exactement au titre utilisateur -> appariement.
    def fake_lookup(title, cfg, limit=12):
        return [
            {
                "film": "http://www.wikidata.org/entity/Q123",
                "filmLabel": "Q123",  # libellé brut : aucun rapport avec le titre
                "title": "Inception",  # wdt:P1476, titre officiel
                "date": "2010-07-16",
                "imdb": "tt1375666",
            }
        ]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Inception"], "year": [2010], "rating": [9]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] == "Q123"
    assert out.loc[0, "imdb"] == "tt1375666"
    # 100 (titre identique) + 10 (bonus année) = 110.
    assert out.loc[0, "match_score"] == 110.0


def test_altlabel_permet_l_appariement(monkeypatch):
    # Ni le filmLabel ni le title ne matchent, mais l'un des altLabels (titre
    # localisé) correspond au titre utilisateur -> appariement.
    def fake_lookup(title, cfg, limit=12):
        return [
            {
                "film": "http://www.wikidata.org/entity/Q456",
                "filmLabel": "Q456",
                "title": "The Shawshank Redemption",  # titre officiel anglais
                # altLabels '|'-séparés : variantes/titres localisés.
                "altLabels": "Évadés|Les Évadés|Shawshank",
                "date": "1994-09-23",
            }
        ]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Les Évadés"], "year": [1994], "rating": [10]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] == "Q456"
    # L'altLabel "Les Évadés" matche exactement (100) + bonus année (10).
    assert out.loc[0, "match_score"] == 110.0


def test_retrocompat_sans_title_ni_altlabels(monkeypatch):
    # Aucun champ title/altLabels : comportement historique, seul filmLabel compte.
    def fake_lookup(title, cfg, limit=12):
        return [
            {
                "film": "http://www.wikidata.org/entity/Q789",
                "filmLabel": "Inception",
                "date": "2010-07-16",
                "imdb": "tt1375666",
            }
        ]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Inception"], "year": [2010], "rating": [9]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] == "Q789"
    assert out.loc[0, "label"] == "Inception"
    assert out.loc[0, "match_score"] == 110.0


def test_retrocompat_filmlabel_hors_sujet_sans_title_rejete(monkeypatch):
    # Sans title/altLabels, un filmLabel sans rapport reste sous le seuil : rejet
    # (le nouveau code ne doit pas "inventer" de match en l'absence de ces champs).
    def fake_lookup(title, cfg, limit=12):
        return [
            {
                "film": "http://www.wikidata.org/entity/Q_HORS_SUJET",
                "filmLabel": "Une Histoire Sans Aucun Rapport",
                "date": "1980-01-01",
            }
        ]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    ratings = pd.DataFrame({"title": ["Inception"], "year": [2010], "rating": [9]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] is None
    assert out.loc[0, "match_score"] is None


def test_filmlabel_hors_sujet_mais_altlabel_correct(monkeypatch):
    # filmLabel et title hors sujet, mais un altLabel matche : on doit franchir le
    # seuil grâce au MEILLEUR score parmi tous les titres candidats.
    def fake_lookup(title, cfg, limit=12):
        return [
            {
                "film": "http://www.wikidata.org/entity/Q999",
                "filmLabel": "Une Histoire Sans Aucun Rapport",
                "title": "Autre Chose Totalement Differente",
                "altLabels": "Pulp Fiction|Fiction Pulpeuse",
                "date": "1994-10-14",
            }
        ]

    monkeypatch.setattr(matching.wikidata, "lookup_film", fake_lookup)

    # Sans année : le score fuzzy de l'altLabel "Pulp Fiction" (100) suffit déjà.
    ratings = pd.DataFrame({"title": ["Pulp Fiction"], "year": [None], "rating": [9]})
    out = matching.match_ratings(ratings, CFG)

    assert out.loc[0, "qid"] == "Q999"
    assert out.loc[0, "match_score"] >= CFG["matching"]["fuzzy_threshold"]


def test_best_title_score_prend_le_max():
    # Helper direct : le titre utilisateur normalisé est comparé à filmLabel,
    # title et chaque altLabel ; on garde le maximum.
    norm_user = matching.normalize_title("Pulp Fiction")
    cand = {
        "filmLabel": "Q999",
        "title": "Autre Chose",
        "altLabels": "Quelque Chose|Pulp Fiction|Encore Autre",
    }
    score = matching.best_title_score(norm_user, cand)
    assert score == 100.0


def test_best_title_score_tolere_champs_absents():
    # Aucun champ exploitable -> 0.0 (et pas d'exception).
    assert matching.best_title_score(matching.normalize_title("Quoi"), {}) == 0.0
    # filmLabel seul, sans title/altLabels : comportement historique.
    cand = {"filmLabel": "Inception"}
    score = matching.best_title_score(matching.normalize_title("Inception"), cand)
    assert score == 100.0
