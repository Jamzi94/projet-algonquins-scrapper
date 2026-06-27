"""Assemblage de la matrice de features combinée : [structuré | embedding].

Contrat d'alignement IMPORTANT :
- `items` est le DataFrame des items, ligne i -> qid items["qid"][i]
- `emb` est un tableau numpy aligné sur `items` : emb[i] correspond à items["qid"][i]
- `structured` est un DataFrame indexé par qid

La même fonction sert à l'entraînement et à la prédiction, ce qui garantit que
les colonnes de features sont identiques des deux côtés.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def feature_matrix(qids, items: pd.DataFrame, emb: np.ndarray, structured: pd.DataFrame) -> np.ndarray:
    pos = {q: i for i, q in enumerate(items["qid"].values)}
    emb_dim = emb.shape[1]
    struct_dim = structured.shape[1]
    rows = []
    for q in qids:
        e = emb[pos[q]] if q in pos else np.zeros(emb_dim, dtype="float32")
        if q in structured.index:
            s = structured.loc[q].values.astype("float32")
        else:
            s = np.zeros(struct_dim, dtype="float32")
        rows.append(np.concatenate([s, e]))
    return np.asarray(rows, dtype="float32")
