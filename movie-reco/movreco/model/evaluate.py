"""Métriques d'évaluation adaptées au cas mono-utilisateur."""
from __future__ import annotations

import numpy as np


def ndcg_at_k(y_true, y_score, k: int = 10) -> float:
    """NDCG@k : qualité du classement par rapport aux notes réelles."""
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    order = np.argsort(-y_score)[:k]
    gains = y_true[order]
    discounts = 1 / np.log2(np.arange(2, len(gains) + 2))
    dcg = float((gains * discounts).sum())
    ideal = np.sort(y_true)[::-1][:k]
    idcg = float((ideal * (1 / np.log2(np.arange(2, len(ideal) + 2)))).sum())
    return dcg / idcg if idcg > 0 else 0.0


def loo_mae(X, y, train_fn) -> float:
    """Erreur absolue moyenne en validation leave-one-out.

    `train_fn(X_train, y_train)` doit renvoyer un modèle compatible avec
    movreco.model.preference.predict.

    Renvoie ``nan`` si moins de 3 films sont notés (n < 3) : le leave-one-out
    n'a alors pas assez de points pour produire une estimation fiable (un seul
    film en apprentissage). Les appelants doivent traiter ``nan`` comme
    « métrique indisponible » et non comme une erreur de zéro.
    """
    from movreco.model.preference import predict

    X = np.asarray(X, dtype="float32")
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 3:
        return float("nan")
    errors = []
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        model = train_fn(X[mask], y[mask])
        pred = predict(model, X[i : i + 1])[0]
        errors.append(abs(pred - y[i]))
    return float(np.mean(errors))


def _sort_key(date):
    """Clé triable pour une date ; les valeurs manquantes passent en premier.

    Renvoie ``(is_present, clé)`` : les ``None``/``NaN``/chaînes vides ont
    ``is_present=0`` et sont donc placés au début (les plus « anciens »), ce qui
    les range dans le TRAIN et jamais dans le holdout récent.
    """
    if date is None:
        return (0, "")
    # NaN (float) : != à lui-même.
    if isinstance(date, float) and date != date:
        return (0, "")
    s = str(date).strip()
    if not s:
        return (0, "")
    return (1, s)


def temporal_ndcg(X, y, dates, train_fn, k: int = 10, holdout_frac: float = 0.3) -> float:
    """NDCG@k sur un découpage temporel (train passé -> holdout récent).

    Trie les films par date croissante (les dates manquantes en premier, donc
    dans le train), entraîne ``train_fn`` sur les plus anciens et évalue le
    classement sur la fraction la plus récente.

    ``train_fn(X_train, y_train)`` doit renvoyer un modèle compatible avec
    movreco.model.preference.predict.

    Renvoie ``nan`` si moins de 4 films sont notés (n < 4) ou si le holdout
    serait vide : le split temporel n'a alors pas assez de points pour une
    estimation utile.
    """
    from movreco.model.preference import predict

    X = np.asarray(X, dtype="float32")
    y = np.asarray(y, dtype=float)
    dates = list(dates)
    n = len(y)
    if n < 4:
        return float("nan")

    order = sorted(range(n), key=lambda i: _sort_key(dates[i]))
    n_holdout = max(1, round(n * holdout_frac))
    if n_holdout >= n:
        return float("nan")

    train_idx = order[: n - n_holdout]
    hold_idx = order[n - n_holdout :]
    if not hold_idx:
        return float("nan")

    model = train_fn(X[train_idx], y[train_idx])
    pred = predict(model, X[hold_idx])
    return ndcg_at_k(y[hold_idx], pred, k)


def format_metric(name: str, value: float) -> str:
    """Formate une métrique pour l'affichage/log (gère ``nan`` proprement)."""
    if value != value:  # nan
        return f"{name} : indisponible (pas assez de films notés)"
    return f"{name} : {value:.4f}"
