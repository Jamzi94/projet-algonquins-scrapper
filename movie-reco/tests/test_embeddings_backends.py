"""Tests du backend d'embedding léger TF-IDF (sans torch) et du repli auto."""
import numpy as np
import pytest

from movreco.features import embeddings as E

# Deux thèmes nettement séparés (espace/SF vs comédie romantique).
SF = [
    "astronaute station spatiale orbite mission galaxie vaisseau",
    "fusee planete extraterrestre exploration cosmos science fiction",
    "voyage interstellaire trou noir gravite astronaute survie",
    "colonie martienne oxygene astronaute ingenieur survie planete",
]
ROM = [
    "mariage amour rencontre comedie romantique couple paris",
    "rupture amoureuse coup de foudre baiser comedie sentimentale",
    "rendez-vous amoureux diner romantique fiancailles mariage",
    "amis amour quiproquo comedie legere relation couple",
]


def _cfg(backend="tfidf", dim=8):
    return {"embeddings": {"backend": backend, "tfidf_dim": dim}}


def test_tfidf_shapes_and_normalisation():
    pytest.importorskip("sklearn")
    emb = E.embed_texts(SF + ROM, _cfg(dim=6))
    assert emb.dtype == np.float32
    assert emb.shape[0] == 8
    # Vecteurs normalisés (norme ~1), compatibles FAISS produit scalaire.
    norms = np.linalg.norm(emb, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_tfidf_capture_la_structure_semantique():
    pytest.importorskip("sklearn")
    # dim << vocabulaire : régime de débruitage (cas réel d'un grand catalogue).
    emb = E.embed_texts(SF + ROM, _cfg(dim=4))
    S = emb @ emb.T
    intra_sf = S[:4, :4][np.triu_indices(4, 1)].mean()
    intra_rom = S[4:, 4:][np.triu_indices(4, 1)].mean()
    inter = S[:4, 4:].mean()
    # Similarité intra-thème nettement supérieure à l'inter-thème.
    assert min(intra_sf, intra_rom) > inter + 0.15


def test_tfidf_deterministe():
    pytest.importorskip("sklearn")
    a = E.embed_texts(SF + ROM, _cfg(dim=8))
    b = E.embed_texts(SF + ROM, _cfg(dim=8))
    assert np.array_equal(a, b)


def test_tfidf_textes_vides_sans_crash():
    pytest.importorskip("sklearn")
    emb = E.embed_texts(["", "  ", "film policier enquete"], _cfg(dim=4))
    assert emb.shape[0] == 3
    assert np.isfinite(emb).all()


def test_auto_repli_sur_tfidf_si_sentence_transformers_absent():
    pytest.importorskip("sklearn")
    # sentence-transformers/torch ne sont pas installés -> auto doit basculer sur tfidf.
    import importlib.util as u

    if u.find_spec("sentence_transformers") is not None:
        pytest.skip("sentence-transformers est installé : le repli n'est pas exercé.")
    with pytest.warns(RuntimeWarning):
        emb = E.embed_texts(SF + ROM, _cfg(backend="auto", dim=6))
    assert emb.shape[0] == 8 and emb.dtype == np.float32
