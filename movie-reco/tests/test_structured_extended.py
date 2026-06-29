"""Tests des features structurées ÉTENDUES (Équipe 2) : acteurs, mots-clés,
langues, durée.

Valide que les colonnes optionnelles ``cast``/``keywords``/``languages``/
``duration`` produisent respectivement des multi-hot ``actor__``/``kw__``/
``lang__`` et une feature numérique ``duration_min`` ; ET la RÉTRO-COMPATIBILITÉ :
un catalogue sans ces colonnes produit exactement le schéma historique
(genres/dir/country/decade), sans colonne parasite.
"""
from __future__ import annotations

import pandas as pd

from movreco.features.structured import build_structured_features


def _items_base() -> pd.DataFrame:
    """Catalogue HISTORIQUE (sans les colonnes enrichies)."""
    return pd.DataFrame(
        {
            "qid": ["Q1", "Q2", "Q3"],
            "genres": ["action|drame", "drame", "comédie|drame"],
            "directors": ["Réalisateur A", "Réalisateur B", "Réalisateur A"],
            "countries": ["France", "France|USA", "USA"],
            "date": ["1995-05-01", "2001-03-15", "2010-12-25"],
        }
    )


def _items_etendu() -> pd.DataFrame:
    """Catalogue ENRICHI avec cast/keywords/languages/duration."""
    df = _items_base()
    df["cast"] = ["Alice|Bob", "Bob|Carole", "Alice"]
    df["keywords"] = ["guerre|espace", "espace", "amour"]
    df["languages"] = ["français", "anglais", "français"]
    # Q2 : durée non numérique -> doit retomber à 0.0.
    df["duration"] = ["120", "inconnu", 95]
    return df


# --------------------------------------------------------------------------- #
# Colonnes enrichies présentes
# --------------------------------------------------------------------------- #
def test_acteurs_multihot_prefixe_actor():
    feats = build_structured_features(_items_etendu())
    assert "actor__Alice" in feats.columns
    assert "actor__Bob" in feats.columns
    assert "actor__Carole" in feats.columns
    # Alice joue dans Q1 et Q3, pas Q2.
    assert feats.loc["Q1", "actor__Alice"] == 1.0
    assert feats.loc["Q3", "actor__Alice"] == 1.0
    assert feats.loc["Q2", "actor__Alice"] == 0.0
    # Bob joue dans Q1 et Q2.
    assert feats.loc["Q1", "actor__Bob"] == 1.0
    assert feats.loc["Q2", "actor__Bob"] == 1.0
    assert feats.loc["Q3", "actor__Bob"] == 0.0


def test_motscles_multihot_prefixe_kw():
    feats = build_structured_features(_items_etendu())
    assert "kw__espace" in feats.columns
    assert "kw__guerre" in feats.columns
    assert "kw__amour" in feats.columns
    # "espace" présent pour Q1 et Q2.
    assert feats.loc["Q1", "kw__espace"] == 1.0
    assert feats.loc["Q2", "kw__espace"] == 1.0
    assert feats.loc["Q3", "kw__espace"] == 0.0
    # "amour" présent pour Q3 uniquement.
    assert feats.loc["Q3", "kw__amour"] == 1.0
    assert feats.loc["Q1", "kw__amour"] == 0.0


def test_langues_multihot_prefixe_lang():
    feats = build_structured_features(_items_etendu())
    assert "lang__français" in feats.columns
    assert "lang__anglais" in feats.columns
    assert feats.loc["Q1", "lang__français"] == 1.0
    assert feats.loc["Q2", "lang__anglais"] == 1.0
    assert feats.loc["Q2", "lang__français"] == 0.0
    assert feats.loc["Q3", "lang__français"] == 1.0


def test_duree_numerique_duration_min():
    feats = build_structured_features(_items_etendu())
    assert "duration_min" in feats.columns
    assert feats.loc["Q1", "duration_min"] == 120.0
    assert feats.loc["Q3", "duration_min"] == 95.0
    # Durée non numérique -> 0.0 (et non NaN).
    assert feats.loc["Q2", "duration_min"] == 0.0


def test_top_actors_borne_le_nombre_de_colonnes_acteurs():
    """Le paramètre top_actors limite bien le nombre de colonnes acteurs."""
    feats = build_structured_features(_items_etendu(), top_actors=1)
    actor_cols = [c for c in feats.columns if c.startswith("actor__")]
    assert len(actor_cols) == 1
    # L'acteur le plus fréquent est conservé en priorité (Alice & Bob = 2 films).
    # Départage déterministe (fréquence puis alpha) -> "actor__Alice".
    assert actor_cols == ["actor__Alice"]


def test_top_keywords_borne_le_nombre_de_colonnes_motscles():
    feats = build_structured_features(_items_etendu(), top_keywords=1)
    kw_cols = [c for c in feats.columns if c.startswith("kw__")]
    assert len(kw_cols) == 1
    # "espace" est le plus fréquent (2 films).
    assert kw_cols == ["kw__espace"]


def test_dtype_float32_avec_colonnes_etendues():
    feats = build_structured_features(_items_etendu())
    assert (feats.dtypes == "float32").all()


def test_determinisme_ordre_colonnes_etendu():
    items = _items_etendu()
    f1 = build_structured_features(items)
    f2 = build_structured_features(items.copy())
    assert list(f1.columns) == list(f2.columns)


# --------------------------------------------------------------------------- #
# RÉTRO-COMPATIBILITÉ : sans les colonnes enrichies, schéma historique strict
# --------------------------------------------------------------------------- #
def test_retrocompat_sans_colonnes_aucune_colonne_parasite():
    feats = build_structured_features(_items_base())
    cols = list(feats.columns)
    # Aucune colonne enrichie ne doit apparaître.
    assert not any(c.startswith("actor__") for c in cols)
    assert not any(c.startswith("kw__") for c in cols)
    assert not any(c.startswith("lang__") for c in cols)
    assert "duration_min" not in cols
    # Le schéma historique reste : uniquement genre/dir/country/decade.
    for c in cols:
        assert c.startswith(("genre__", "dir__", "country__", "decade_")), c


def test_retrocompat_schema_identique_au_comportement_historique():
    """Sans colonnes enrichies, le schéma est strictement celui d'avant."""
    base_items = _items_base()
    feats_base = build_structured_features(base_items)

    # Mêmes données mais en ajoutant PUIS retirant les colonnes enrichies :
    # le résultat doit retomber sur le schéma historique exact.
    enrichi = _items_etendu().drop(
        columns=["cast", "keywords", "languages", "duration"]
    )
    feats_retire = build_structured_features(enrichi)

    assert list(feats_base.columns) == list(feats_retire.columns)
    pd.testing.assert_frame_equal(feats_base, feats_retire)


def test_colonnes_enrichies_partielles_ignore_les_absentes():
    """Si seules certaines colonnes enrichies sont présentes, on n'ajoute que
    celles-là (les autres restent ignorées proprement)."""
    df = _items_base()
    df["cast"] = ["Alice|Bob", "Bob", "Alice"]  # seulement le casting
    feats = build_structured_features(df)
    assert any(c.startswith("actor__") for c in feats.columns)
    # keywords/languages/duration absents -> aucune colonne correspondante.
    assert not any(c.startswith("kw__") for c in feats.columns)
    assert not any(c.startswith("lang__") for c in feats.columns)
    assert "duration_min" not in feats.columns


def test_columns_reindexe_la_sortie_etendue():
    """Le paramètre `columns` continue de réindexer même avec colonnes enrichies."""
    items = _items_etendu()
    schema = list(build_structured_features(items).columns)
    # Ajout d'une colonne absente : doit être créée à 0.
    cible = schema + ["actor__Inconnu"]
    out = build_structured_features(items, columns=cible)
    assert list(out.columns) == cible
    assert (out["actor__Inconnu"] == 0.0).all()
