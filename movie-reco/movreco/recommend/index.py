"""Index FAISS pour la recherche de plus proches voisins (similarité cosinus)."""
from __future__ import annotations

import numpy as np


def build_index(emb: np.ndarray):
    """Construit un index plat à produit scalaire (cosinus si vecteurs normalisés)."""
    import faiss

    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(np.ascontiguousarray(emb.astype("float32")))
    return index


def search(index, query_vec: np.ndarray, k: int):
    """Renvoie (indices, scores) des k plus proches voisins du vecteur requête."""
    q = np.ascontiguousarray(query_vec.reshape(1, -1).astype("float32"))
    distances, indices = index.search(q, k)
    return indices[0], distances[0]


def save_index(index, path) -> None:
    import faiss

    faiss.write_index(index, str(path))


def load_index(path):
    import faiss

    return faiss.read_index(str(path))


def build_or_load(emb: np.ndarray, path):
    """Réutilise l'index persistant si compatible, sinon le (re)construit.

    Charge l'index depuis `path` et le renvoie s'il existe et que son `ntotal`
    ET sa dimension `d` correspondent à `emb` (shape[0] et shape[1]). Sinon
    (absent, corrompu, désaligné ou dimension changée), construit un nouvel index,
    l'écrit à `path` et le renvoie. Garantit l'alignement avec les lignes de `emb`.
    """
    from pathlib import Path

    p = Path(path)
    if p.exists():
        try:
            idx = load_index(p)
            if idx.ntotal == emb.shape[0] and idx.d == emb.shape[1]:
                return idx
        except Exception:
            pass

    index = build_index(emb)
    p.parent.mkdir(parents=True, exist_ok=True)
    save_index(index, p)
    return index
