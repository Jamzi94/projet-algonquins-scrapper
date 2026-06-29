"""Tests hors-ligne du NDCG temporel (Équipe 3).

Vérifie que ``evaluate.temporal_ndcg`` réalise un découpage train passé ->
holdout récent, renvoie un score dans [0, 1] sur un signal synthétique, et
renvoie ``nan`` quand il n'y a pas assez de films notés. Aucune dépendance
réseau ; nécessite LightGBM OU scikit-learn (pour ``preference.train``).
"""
import numpy as np
import pytest

# preference.train s'appuie sur LightGBM, avec repli scikit-learn. On saute le
# module si aucun des deux n'est installé.
try:
    import lightgbm  # noqa: F401
except ImportError:
    pytest.importorskip("sklearn")

from movreco.model import preference
from movreco.model.evaluate import temporal_ndcg


def _train_fn(X, y):
    return preference.train(X, y, None)


def _synthetic(n: int = 12, d: int = 4):
    """X synthétique où y corrèle fortement avec la 1re colonne (signal net)."""
    rng = np.random.default_rng(0)
    X = rng.standard_normal((n, d)).astype("float32")
    y = (X[:, 0] * 5.0 + 5.0).astype(float)  # note ~ colonne 0, échelle 0-10
    dates = [f"20{10 + i:02d}-01-01" for i in range(n)]  # dates croissantes
    return X, y, dates


def test_temporal_ndcg_dans_intervalle_unite():
    X, y, dates = _synthetic()
    v = temporal_ndcg(X, y, dates, _train_fn, k=10, holdout_frac=0.3)
    assert isinstance(v, float)
    assert 0.0 <= v <= 1.0


def test_temporal_ndcg_nan_si_trop_peu_de_films():
    # n < 4 -> nan
    X = np.eye(3, dtype="float32")
    y = [1.0, 2.0, 3.0]
    dates = ["2020", "2021", "2022"]
    v = temporal_ndcg(X, y, dates, _train_fn)
    assert v != v  # nan


def test_temporal_ndcg_nan_si_holdout_vide():
    # holdout_frac=0 -> n_holdout=1 (max(1, ...)) reste défini ; on force le cas
    # où le holdout couvre tout (frac=1.0 -> n_holdout >= n -> nan).
    X, y, dates = _synthetic(n=6)
    v = temporal_ndcg(X, y, dates, _train_fn, holdout_frac=1.0)
    assert v != v  # nan


def test_temporal_ndcg_dates_manquantes_vont_au_train():
    # Les dates None/NaN doivent être triées en premier (donc dans le train),
    # jamais dans le holdout récent : la fonction reste calculable.
    X, y, _ = _synthetic(n=8)
    dates = [None, float("nan"), "", "2018", "2019", "2020", "2021", "2022"]
    v = temporal_ndcg(X, y, dates, _train_fn, holdout_frac=0.25)
    assert isinstance(v, float)
    assert 0.0 <= v <= 1.0
