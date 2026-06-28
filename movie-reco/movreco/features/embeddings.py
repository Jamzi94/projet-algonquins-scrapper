"""Calcul des embeddings sémantiques des textes (synopsis ou titres).

Deux backends, choisis par ``config.yaml > embeddings.backend`` :

- ``sentence-transformers`` : modèle multilingue de qualité (nécessite torch).
- ``tfidf`` : repli LÉGER (scikit-learn, déjà installé), SANS torch ni
  téléchargement — TF-IDF puis réduction de dimension (SVD tronquée) et
  normalisation L2. Idéal quand sentence-transformers/torch ne sont pas
  disponibles ; fonctionne aussi sur les seuls titres (mode hors-ligne).
- ``auto`` (défaut) : tente sentence-transformers, bascule automatiquement sur
  ``tfidf`` s'il est indisponible.

Toutes les sorties sont des vecteurs float32 normalisés (norme 1), compatibles
avec l'index FAISS à produit scalaire (cosinus).
"""
from __future__ import annotations

import warnings

import numpy as np

_MODEL = None


def _model(cfg: dict):
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(cfg["embeddings"]["model"])
    return _MODEL


def _embed_sentence_transformers(texts, cfg: dict) -> np.ndarray:
    model = _model(cfg)
    emb = model.encode(
        list(texts),
        batch_size=cfg["embeddings"].get("batch_size", 64),
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return np.asarray(emb, dtype="float32")


def _embed_tfidf(texts, cfg: dict) -> np.ndarray:
    """Backend léger : TF-IDF -> SVD tronquée -> normalisation L2 (sans torch)."""
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    ecfg = cfg.get("embeddings", {})
    dim = int(ecfg.get("tfidf_dim", 256))
    # Texte vide -> placeholder pour éviter une colonne entièrement nulle.
    docs = [t if isinstance(t, str) and t.strip() else " " for t in texts]

    vec = TfidfVectorizer(
        strip_accents="unicode",
        lowercase=True,
        sublinear_tf=True,
        max_features=int(ecfg.get("tfidf_max_features", 50000)),
    )
    X = vec.fit_transform(docs)
    n_samples, n_features = X.shape

    # SVD impossible (corpus minuscule) -> TF-IDF dense tronqué/complété à `dim`.
    if n_samples <= 2 or n_features <= 1:
        dense = X.toarray().astype("float32")
        if dense.shape[1] >= dim:
            emb = dense[:, :dim]
        else:
            emb = np.zeros((n_samples, dim), dtype="float32")
            emb[:, : dense.shape[1]] = dense
    else:
        n_comp = max(1, min(dim, n_features - 1, n_samples - 1))
        svd = TruncatedSVD(n_components=n_comp, random_state=0)
        emb = svd.fit_transform(X)

    emb = normalize(np.asarray(emb, dtype="float32"))
    return emb.astype("float32")


def embed_texts(texts, cfg: dict) -> np.ndarray:
    """Encode une liste de textes en vecteurs denses normalisés (float32).

    Le backend est choisi par ``cfg["embeddings"]["backend"]`` :
    ``sentence-transformers`` | ``tfidf`` | ``auto`` (défaut).
    """
    backend = cfg.get("embeddings", {}).get("backend", "auto")

    if backend == "tfidf":
        return _embed_tfidf(texts, cfg)
    if backend == "sentence-transformers":
        return _embed_sentence_transformers(texts, cfg)
    # auto : qualité si disponible, repli léger sinon.
    try:
        return _embed_sentence_transformers(texts, cfg)
    except ImportError:
        warnings.warn(
            "sentence-transformers indisponible : repli sur le backend 'tfidf' "
            "(léger, sans torch). Définissez embeddings.backend pour choisir.",
            RuntimeWarning,
            stacklevel=2,
        )
        return _embed_tfidf(texts, cfg)
