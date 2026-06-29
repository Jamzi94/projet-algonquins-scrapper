"""Tests hors-ligne de la persistance de l'index FAISS (Équipe 2).

Vérifie le helper ``index.build_or_load`` (création puis réutilisation) et le
câblage ``pipeline.recommend(..., index_path=...)``. Aucune dépendance réseau.
"""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("faiss")

from movreco.recommend import index as faiss_index
from movreco.recommend import pipeline


def _norm_emb(n: int = 20, d: int = 8) -> np.ndarray:
    """Embeddings déterministes, normalisés (cosinus via produit scalaire)."""
    rng = np.random.default_rng(0)
    emb = rng.standard_normal((n, d)).astype("float32")
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    return emb


def _items(n: int) -> pd.DataFrame:
    """Catalogue minimal cohérent avec ``emb`` (n lignes : qid/label/popularity)."""
    return pd.DataFrame(
        {
            "qid": [f"Q{i}" for i in range(n)],
            "label": [f"Film {i}" for i in range(n)],
            "popularity": np.arange(n, dtype=float),
        }
    )


def test_build_or_load_cree_puis_reutilise(tmp_path):
    emb = _norm_emb()
    path = tmp_path / "x.faiss"
    assert not path.exists()

    idx1 = faiss_index.build_or_load(emb, path)
    assert path.exists()  # premier appel : construction + écriture
    assert idx1.ntotal == emb.shape[0]

    idx2 = faiss_index.build_or_load(emb, path)  # second appel : réutilisation
    assert idx2.ntotal == emb.shape[0]


def test_build_or_load_reconstruit_si_desaligne(tmp_path):
    path = tmp_path / "x.faiss"
    faiss_index.build_or_load(_norm_emb(20, 8), path)

    # emb plus court : ntotal != shape[0] -> reconstruction et réécriture.
    emb2 = _norm_emb(10, 8)
    idx = faiss_index.build_or_load(emb2, path)
    assert idx.ntotal == 10
    assert path.exists()


def test_build_or_load_reconstruit_si_dimension_changee(tmp_path):
    """Meme ntotal mais dimension differente (ex: changement de modele) -> reconstruit."""
    path = tmp_path / "x.faiss"
    faiss_index.build_or_load(_norm_emb(10, 8), path)

    emb2 = _norm_emb(10, 16)  # meme nb de lignes, dimension differente
    idx = faiss_index.build_or_load(emb2, path)
    assert idx.ntotal == 10 and idx.d == 16
    # L'index reconstruit reste utilisable (pas d'AssertionError FAISS au search).
    sub_idx, _ = faiss_index.search(idx, emb2[0], k=3)
    assert len(sub_idx) == 3


def test_recommend_persiste_et_reutilise_l_index(tmp_path):
    emb = _norm_emb()
    items = _items(len(emb))
    index_path = tmp_path / "reco.faiss"
    rated_qids = ["Q0", "Q1", "Q2"]
    ratings = [10, 8, 2]
    cfg = {"recommend": {"top_n": 5, "candidates": 15}}

    r1 = pipeline.recommend(
        items, emb, rated_qids, ratings, mode="mvp", cfg=cfg, index_path=index_path
    )
    assert isinstance(r1, pd.DataFrame) and not r1.empty
    assert list(r1.columns) == ["qid", "label", "score"]
    assert index_path.exists()  # l'index a été écrit sur disque

    # Second appel : l'index persistant est réutilisé, le résultat reste valide.
    r2 = pipeline.recommend(
        items, emb, rated_qids, ratings, mode="mvp", cfg=cfg, index_path=index_path
    )
    assert not r2.empty
    assert index_path.exists()
    # Les films notés ne sont jamais recommandés.
    assert not set(r2["qid"]) & set(rated_qids)


def test_recommend_sans_index_path_inchange(tmp_path):
    emb = _norm_emb()
    items = _items(len(emb))
    cfg = {"recommend": {"top_n": 5, "candidates": 15}}
    r = pipeline.recommend(
        items, emb, ["Q0", "Q1", "Q2"], [10, 8, 2], mode="mvp", cfg=cfg
    )
    assert not r.empty  # index construit en mémoire, aucun fichier requis
