"""Tests du câblage explain de l'API (Équipe 4) — hors-ligne, LLM monkeypatché.

POST /recommend accepte un champ optionnel ``explain: bool = false``. Quand il
vaut ``true`` ET que ``cfg.llm.enabled`` est vrai, le service appelle la couche
LLM (``rerank.rerank_and_explain``) pour attacher une raison à chaque résultat
(champ optionnel ``raison`` de ``ScoredMovie``). Sans ``llm.enabled`` (ou
``explain: false``), l'option est ignorée silencieusement : aucune raison, aucune
erreur, contrat inchangé.

La couche LLM n'est JAMAIS réellement appelée : on monkeypatche
``movreco.llm.rerank.rerank_and_explain`` (l'attribut que le service résout via
``from movreco.llm import rerank``).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests._synthetic import build_synthetic_catalog  # noqa: E402


N_GENRES = 4
PER_GENRE = 15


def _ctx(tmp_path, llm_enabled: bool):
    """Catalogue synthétique dont le cfg active (ou non) la couche LLM."""
    meta = build_synthetic_catalog(
        tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE, dim=16, seed=0
    )
    cfg = meta["cfg"]
    llm = dict(cfg.get("llm", {}) or {})
    llm["enabled"] = llm_enabled
    llm.setdefault("model", "claude-sonnet-4-6")
    cfg["llm"] = llm
    return meta


def _fake_rerank_factory(record):
    """Fabrique un faux rerank_and_explain qui attache une raison par candidat.

    Mémorise dans ``record`` les arguments reçus (pour vérifier l'appel), puis
    renvoie une raison déterministe par position de candidat.
    """

    def fake(liked_titles, candidates, cfg, client=None):
        record["called"] = True
        record["liked"] = list(liked_titles)
        record["candidates"] = list(candidates)
        record["client"] = client
        return [
            {"index": i, "raison": f"raison {i}"} for i in range(len(candidates))
        ]

    return fake


def _payload(ctx, explain=None):
    liked = ctx["genre_to_qids"]["Genre 0"][:3]
    body = {
        "ratings": [{"qid": q, "rating": 5.0} for q in liked],
        "mode": "mvp",
        "n": 5,
    }
    if explain is not None:
        body["explain"] = explain
    return body


# --------------------------------------------------------------------------- #
# explain: true + llm.enabled -> raisons attachées
# --------------------------------------------------------------------------- #
def test_explain_true_avec_llm_attache_raisons(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, llm_enabled=True)
    record = {}
    from movreco.llm import rerank

    monkeypatch.setattr(rerank, "rerank_and_explain", _fake_rerank_factory(record))

    from movreco.api.app import create_app

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        resp = c.post("/recommend", json=_payload(ctx, explain=True))
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 5
        # Chaque résultat porte une raison non vide.
        for i, r in enumerate(results):
            assert r.get("raison") == f"raison {i}"

    # La couche LLM a bien été appelée, avec le client par défaut (None).
    assert record.get("called") is True
    assert record.get("client") is None
    # Les candidats transmis sont les labels recommandés (5 attendus).
    assert len(record["candidates"]) == 5


# --------------------------------------------------------------------------- #
# explain: false -> pas de raison (et LLM non appelé)
# --------------------------------------------------------------------------- #
def test_explain_false_pas_de_raison(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, llm_enabled=True)
    record = {}
    from movreco.llm import rerank

    monkeypatch.setattr(rerank, "rerank_and_explain", _fake_rerank_factory(record))

    from movreco.api.app import create_app

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        resp = c.post("/recommend", json=_payload(ctx, explain=False))
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 5
        assert all(r.get("raison") is None for r in results)

    # explain=false court-circuite l'appel LLM.
    assert record.get("called") is None


def test_explain_absent_pas_de_raison(tmp_path, monkeypatch):
    # Champ explain absent du corps : défaut false, donc pas de raison, pas d'appel.
    ctx = _ctx(tmp_path, llm_enabled=True)
    record = {}
    from movreco.llm import rerank

    monkeypatch.setattr(rerank, "rerank_and_explain", _fake_rerank_factory(record))

    from movreco.api.app import create_app

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        resp = c.post("/recommend", json=_payload(ctx, explain=None))
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert all(r.get("raison") is None for r in results)

    assert record.get("called") is None


# --------------------------------------------------------------------------- #
# explain: true mais llm désactivé -> ignoré silencieusement
# --------------------------------------------------------------------------- #
def test_explain_true_sans_llm_ignore_silencieusement(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, llm_enabled=False)
    record = {}
    from movreco.llm import rerank

    # Même si le rerank est patché, llm.enabled=false doit empêcher tout appel.
    monkeypatch.setattr(rerank, "rerank_and_explain", _fake_rerank_factory(record))

    from movreco.api.app import create_app

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        resp = c.post("/recommend", json=_payload(ctx, explain=True))
        # Pas d'erreur : l'option est simplement ignorée.
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 5
        assert all(r.get("raison") is None for r in results)

    assert record.get("called") is None


# --------------------------------------------------------------------------- #
# Tolérance : un rerank qui échoue (None) ne casse rien
# --------------------------------------------------------------------------- #
def test_explain_true_rerank_renvoie_none_pas_d_erreur(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, llm_enabled=True)
    from movreco.llm import rerank

    def fake_none(liked_titles, candidates, cfg, client=None):
        return None

    monkeypatch.setattr(rerank, "rerank_and_explain", fake_none)

    from movreco.api.app import create_app

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        resp = c.post("/recommend", json=_payload(ctx, explain=True))
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 5
        # Aucun champ raison attaché, mais pas d'erreur.
        assert all(r.get("raison") is None for r in results)
