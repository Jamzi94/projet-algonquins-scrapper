"""Tests de l'outil de tuning hors-ligne (Équipe 3) sur catalogue synthétique.

On valide ``recommend.tuning.evaluate_recall`` et ``recommend.tuning.sweep`` sur
un catalogue synthétique groupé par genre (cf. tests/_synthetic.py). Aucun réseau,
aucun sentence-transformers ; le pipeline tire ``faiss`` -> ``importorskip``.

On vérifie :
  - ``evaluate_recall`` renvoie des métriques cohérentes (0 <= recall <= 1,
    0 <= ndcg <= 1, ``n_holdout`` > 0) et est déterministe (graine) ;
  - le holdout est bien retrouvable : sur un catalogue à genres bien séparés, des
    films cachés du genre aimé doivent réapparaître (recall > 0) ;
  - ``sweep`` renvoie une liste NON vide couvrant tout le produit cartésien du
    grid, triée par recall@k décroissant, sans muter la config de l'appelant ;
  - dégradation propre : trop peu de notes -> nan / n_holdout = 0.
"""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("faiss")

from movreco.recommend import tuning  # noqa: E402
from tests._synthetic import build_synthetic_catalog  # noqa: E402


N_GENRES = 4
PER_GENRE = 15


@pytest.fixture()
def ctx(tmp_path):
    """Catalogue synthétique + un jeu de notes RICHE sur le genre aimé.

    Le ``rated.parquet`` synthétique ne contient que 3 films aimés : on construit
    ici un jeu de notes plus fourni (plusieurs films du genre 0 fortement notés,
    quelques films du genre 1 faiblement notés) pour avoir un holdout non trivial.
    """
    meta = build_synthetic_catalog(
        tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE, dim=16, seed=0
    )
    liked = meta["genre_to_qids"]["Genre 0"][:8]   # 8 films très aimés
    disliked = meta["genre_to_qids"]["Genre 1"][:4]  # 4 films peu aimés
    rated_qids = liked + disliked
    ratings = [5.0] * len(liked) + [1.0] * len(disliked)
    meta["rated_qids"] = rated_qids
    meta["ratings"] = ratings
    meta["liked"] = liked
    return meta


def _structured(ctx):
    return pd.read_parquet(ctx["data_dir"] / "processed" / "structured.parquet")


# --------------------------------------------------------------------------- #
# evaluate_recall
# --------------------------------------------------------------------------- #
def test_evaluate_recall_metriques_coherentes(ctx):
    res = tuning.evaluate_recall(
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        ctx["rated_qids"],
        ctx["ratings"],
        ctx["cfg"],
        k=10,
        holdout_frac=0.3,
        seed=0,
    )
    assert set(res.keys()) == {"recall_at_k", "ndcg_at_k", "n_holdout"}
    assert res["n_holdout"] > 0
    # Bornes des métriques.
    assert 0.0 <= res["recall_at_k"] <= 1.0
    assert 0.0 <= res["ndcg_at_k"] <= 1.0


def test_evaluate_recall_retrouve_le_holdout(ctx):
    # Genres bien séparés : cacher des films du genre aimé et recommander sur le
    # reste doit en retrouver une partie -> recall strictement positif.
    res = tuning.evaluate_recall(
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        ctx["rated_qids"],
        ctx["ratings"],
        ctx["cfg"],
        k=10,
        holdout_frac=0.3,
        seed=0,
    )
    assert res["recall_at_k"] > 0.0


def test_evaluate_recall_deterministe(ctx):
    args = (
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        ctx["rated_qids"],
        ctx["ratings"],
        ctx["cfg"],
    )
    a = tuning.evaluate_recall(*args, k=10, holdout_frac=0.3, seed=0)
    b = tuning.evaluate_recall(*args, k=10, holdout_frac=0.3, seed=0)
    assert a == b


def test_evaluate_recall_ne_mute_pas_cfg(ctx):
    before = copy.deepcopy(ctx["cfg"])
    tuning.evaluate_recall(
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        ctx["rated_qids"],
        ctx["ratings"],
        ctx["cfg"],
        k=10,
        holdout_frac=0.3,
        seed=0,
    )
    assert ctx["cfg"] == before


def test_evaluate_recall_trop_peu_de_notes(ctx):
    # Une seule note : impossible de constituer (train, holdout) -> nan, n=0.
    res = tuning.evaluate_recall(
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        [ctx["liked"][0]],
        [5.0],
        ctx["cfg"],
        k=10,
    )
    assert res["n_holdout"] == 0
    assert math.isnan(res["recall_at_k"])
    assert math.isnan(res["ndcg_at_k"])


# --------------------------------------------------------------------------- #
# sweep
# --------------------------------------------------------------------------- #
def test_sweep_couvre_le_grid_et_trie(ctx):
    grid = {
        "mmr_lambda": [0.5, 0.9],
        "serendipity": [0.0, 0.2],
        "popularity_penalty": [0.0],
        "candidates": [60],
    }
    rows = tuning.sweep(
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        ctx["rated_qids"],
        ctx["ratings"],
        grid,
        ctx["cfg"],
        k=10,
        holdout_frac=0.3,
    )
    # Produit cartésien : 2 * 2 * 1 * 1 = 4 combinaisons.
    assert len(rows) == 4
    for row in rows:
        assert set(row.keys()) == {"params", "recall_at_k", "ndcg_at_k", "n_holdout"}
        assert set(row["params"].keys()) == set(grid.keys())
        assert row["params"]["mmr_lambda"] in grid["mmr_lambda"]
        assert row["params"]["candidates"] in grid["candidates"]

    # Toutes les combinaisons du grid sont présentes (pas de doublon, couverture).
    seen = {tuple(sorted(r["params"].items())) for r in rows}
    assert len(seen) == 4

    # Tri par recall@k décroissant (nan en fin, traités comme -inf).
    def _rank(v):
        return v if v == v else float("-inf")

    recalls = [_rank(r["recall_at_k"]) for r in rows]
    assert recalls == sorted(recalls, reverse=True)


def test_sweep_non_vide_et_cfg_intact(ctx):
    grid = {"mmr_lambda": [0.5, 0.7], "candidates": [60]}
    before = copy.deepcopy(ctx["cfg"])
    rows = tuning.sweep(
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        ctx["rated_qids"],
        ctx["ratings"],
        grid,
        ctx["cfg"],
        k=10,
    )
    assert len(rows) == 2
    # La config de l'appelant n'est jamais mutée par le balayage.
    assert ctx["cfg"] == before


def test_sweep_grid_vide_donne_une_evaluation(ctx):
    # Grid vide : on évalue quand même la config de base une fois (combinaison vide).
    rows = tuning.sweep(
        ctx["items"],
        ctx["emb"],
        _structured(ctx),
        ctx["rated_qids"],
        ctx["ratings"],
        {},
        ctx["cfg"],
        k=10,
    )
    assert len(rows) == 1
    assert rows[0]["params"] == {}
