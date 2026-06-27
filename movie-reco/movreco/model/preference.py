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
    try:
        import lightgbm as lgb

        dtrain = lgb.Dataset(X, label=y)
        params = {
            "objective": "regression_l1",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "min_data_in_leaf": 5,
            "verbose": -1,
        }
        booster = lgb.train(params, dtrain, num_boost_round=300)
        return ("lgb", booster)
    except Exception:
        from sklearn.ensemble import GradientBoostingRegressor

        model = GradientBoostingRegressor(random_state=0)
        model.fit(X, y)
        return ("sk", model)


def predict(model, X) -> np.ndarray:
    _, estimator = model
    return np.asarray(estimator.predict(np.asarray(X, dtype="float32")), dtype=float)


def save(model, path) -> None:
    import joblib

    joblib.dump(model, path)


def load(path):
    import joblib

    return joblib.load(path)
