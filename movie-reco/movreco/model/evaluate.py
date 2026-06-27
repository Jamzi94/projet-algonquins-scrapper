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
