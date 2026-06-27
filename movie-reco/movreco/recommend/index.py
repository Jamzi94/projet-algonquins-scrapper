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
