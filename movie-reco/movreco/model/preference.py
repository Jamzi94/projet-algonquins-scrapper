"""Modèle de préférence supervisé mono-utilisateur.

Entraîne un régresseur à prédire la note de l'utilisateur à partir des features
d'un film. LightGBM par défaut, repli sur scikit-learn s'il n'est pas disponible.
Un modèle est un tuple (type, estimateur) pour rester sérialisable simplement.
"""
from __future__ import annotations

import numpy as np


def train(X, y, cfg: dict | None = None):
    X = np.asarray(X, dtype="float32")
    y = np.asarray(y, dtype=float)
    n = len(y)
    # num_boost_round / n_estimators adaptatif au très petit n (cold-start).
    n_rounds = max(50, min(300, 40 * n))
    try:
        import lightgbm as lgb
    except ImportError:
        # Repli scikit-learn UNIQUEMENT si LightGBM est absent.
        from sklearn.ensemble import GradientBoostingRegressor

        model = GradientBoostingRegressor(
            n_estimators=n_rounds,
            max_depth=2,
            random_state=0,
        )
        model.fit(X, y)
        return ("sk", model)

    # Hors try/except : une vraie erreur d'entraînement LightGBM se propage.
    dtrain = lgb.Dataset(X, label=y)
    params = {
        "objective": "regression_l1",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "min_data_in_leaf": 5,
        # Régularisation pour le très petit n (cold-start).
        "lambda_l1": 1.0,
        "lambda_l2": 1.0,
        "max_depth": 4,
        "seed": 0,
        "deterministic": True,
        "verbose": -1,
    }
    booster = lgb.train(params, dtrain, num_boost_round=n_rounds)
    return ("lgb", booster)


def predict(model, X) -> np.ndarray:
    _, estimator = model
    return np.asarray(estimator.predict(np.asarray(X, dtype="float32")), dtype=float)


def save(model, path) -> None:
    import joblib

    joblib.dump(model, path)


def load(path):
    import joblib

    return joblib.load(path)
