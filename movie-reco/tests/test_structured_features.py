"""Tests de structured.build_structured_features : déterminisme, multihot,
décennie, et réindexation via le paramètre `columns`."""
from __future__ import annotations

import pandas as pd

from movreco.features.structured import build_structured_features


def _items() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "qid": ["Q1", "Q2", "Q3"],
            "genres": ["action|drame", "drame", "comédie|drame"],
            "directors": ["Réalisateur A", "Réalisateur B", "Réalisateur A"],
            "countries": ["France", "France|USA", "USA"],
            "date": ["1995-05-01", "2001-03-15", "2010-12-25"],
        }
    )


def test_index_par_qid():
    feats = build_structured_features(_items())
    assert list(feats.index) == ["Q1", "Q2", "Q3"]
    assert feats.index.name == "qid"


def test_determinisme_de_l_ordre_des_colonnes():
    items = _items()
    f1 = build_structured_features(items)
    f2 = build_structured_features(items.copy())
    # même entrée -> mêmes colonnes, dans le même ordre
    assert list(f1.columns) == list(f2.columns)


def test_multihot_genre_present_vaut_1():
    feats = build_structured_features(_items())
    # "drame" présent pour les 3 films
    assert "genre__drame" in feats.columns
    assert feats.loc["Q1", "genre__drame"] == 1.0
    assert feats.loc["Q2", "genre__drame"] == 1.0
    assert feats.loc["Q3", "genre__drame"] == 1.0
    # "action" présent pour Q1 uniquement
    assert feats.loc["Q1", "genre__action"] == 1.0
    assert feats.loc["Q2", "genre__action"] == 0.0
    assert feats.loc["Q3", "genre__action"] == 0.0


def test_multihot_pays_multiple():
    feats = build_structured_features(_items())
    # Q2 a France|USA
    assert feats.loc["Q2", "country__France"] == 1.0
    assert feats.loc["Q2", "country__USA"] == 1.0
    assert feats.loc["Q1", "country__USA"] == 0.0


def test_decennie_correcte():
    feats = build_structured_features(_items())
    # 1995 -> 1990, 2001 -> 2000, 2010 -> 2010
    assert feats.loc["Q1", "decade_1990"] == 1.0
    assert feats.loc["Q2", "decade_2000"] == 1.0
    assert feats.loc["Q3", "decade_2010"] == 1.0
    # exclusivité : Q1 n'est pas dans 2000
    assert feats.loc["Q1", "decade_2000"] == 0.0


def test_columns_none_vs_liste_reindexation_et_zeros():
    items = _items()
    base = build_structured_features(items, columns=None)

    # On impose un schéma fixe : une colonne connue + une colonne absente.
    cible = ["genre__drame", "colonne_inexistante"]
    out = build_structured_features(items, columns=cible)

    assert list(out.columns) == cible
    # colonne connue : valeurs préservées
    assert out.loc["Q1", "genre__drame"] == base.loc["Q1", "genre__drame"]
    # colonne absente du calcul : remplie de 0
    assert (out["colonne_inexistante"] == 0.0).all()


def test_columns_garantit_schema_train_predict_identique():
    train_items = _items()
    feats_train = build_structured_features(train_items)
    schema = list(feats_train.columns)

    # un seul film en prédiction, genres différents -> doit suivre le schéma train
    pred_items = pd.DataFrame(
        {
            "qid": ["Q9"],
            "genres": ["western"],
            "directors": ["Inconnu"],
            "countries": ["Italie"],
            "date": ["1966-01-01"],
        }
    )
    feats_pred = build_structured_features(pred_items, columns=schema)

    assert list(feats_pred.columns) == schema
    # genres/pays inconnus du schéma train -> 0 partout pour ces colonnes
    assert (feats_pred.loc["Q9"] == 0.0).all()


def test_dtype_float32():
    feats = build_structured_features(_items())
    assert (feats.dtypes == "float32").all()
