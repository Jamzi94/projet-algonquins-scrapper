"""Tests d'intégration de l'API FastAPI de synergie (sans Mongo, hors-ligne).

On exerce :mod:`integrated_api` (la petite app qui expose le pont
:class:`recommender_bridge.SynergyEngine`) via ``TestClient``, sur un catalogue
synthétique groupé par genre. On valide le CONTRAT D'API (clés JSON, codes) ET la
PERTINENCE (un goût pour un genre -> des films du même genre).

Aucun réseau, aucun sentence-transformers : tout repose sur le catalogue
synthétique de movie-reco (``tests/_synthetic.build_synthetic_catalog``).
``fastapi`` est facultatif : on saute le module s'il est absent.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Chemins : backend (pour integrated_api / recommender_bridge), movie-reco et son
# helper de test (movreco + _synthetic ne sont pas pip-installés).
# parents[1] -> swipe-movie/backend ; parents[3] -> racine du dépôt.
# --------------------------------------------------------------------------- #
_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MOVRECO_ROOT = _REPO_ROOT / "movie-reco"
for _p in (str(_BACKEND), str(_MOVRECO_ROOT), str(_MOVRECO_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# fastapi facultatif ; movreco requis pour la synergie.
pytest.importorskip("fastapi")
pytest.importorskip("movreco")

from fastapi.testclient import TestClient  # noqa: E402

from _synthetic import build_synthetic_catalog  # noqa: E402

from integrated_api import create_app  # noqa: E402


N_GENRES = 4
PER_GENRE = 15
DIM = 16
SEED = 0


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def ctx(tmp_path):
    """Catalogue synthétique en tmp_path + métadonnées (genres, qids, cfg)."""
    return build_synthetic_catalog(
        tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE, dim=DIM, seed=SEED
    )


@pytest.fixture()
def client(ctx):
    """Client de test avec lifespan déclenché (moteur movreco chargé)."""
    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# GET /api/provider-status
# --------------------------------------------------------------------------- #
def test_provider_status(client):
    resp = client.get("/api/provider-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "wikidata+wikipedia"
    assert body["tmdb_enabled"] is False
    assert body["license"] == "CC0 + CC BY-SA"
    assert body["catalog_size"] == N_GENRES * PER_GENRE


# --------------------------------------------------------------------------- #
# GET /api/catalog
# --------------------------------------------------------------------------- #
def test_catalog(client, ctx):
    resp = client.get("/api/catalog", params={"limit": 7})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 7
    qid_to_genre = ctx["qid_to_genre"]
    for content in results:
        assert content["type"] == "movie"
        assert content["source"] == "wikidata"
        assert content["id"] in qid_to_genre
        assert content["genres"] == [qid_to_genre[content["id"]]]


# --------------------------------------------------------------------------- #
# POST /api/recommendations — PERTINENCE
# --------------------------------------------------------------------------- #
def test_recommendations_pertinence(client, ctx):
    """Aimer 3 films d'un genre -> top-N majoritairement du même genre."""
    genre_to_qids = ctx["genre_to_qids"]
    qid_to_genre = ctx["qid_to_genre"]
    liked_genre = ctx["genre_names"][0]
    liked = genre_to_qids[liked_genre][:3]

    body = {"swipes": [{"qid": q, "action": "like"} for q in liked], "n": 10}
    resp = client.post("/api/recommendations", json=body)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 10
    for r in results:
        assert set(r) >= {"id", "title", "score", "reasons"}

    genres = Counter(qid_to_genre[r["id"]] for r in results)
    assert genres[liked_genre] / len(results) >= 0.60, f"pertinence: {genres}"
    # Les films swipés ne sont pas re-proposés.
    assert set(liked).isdisjoint({r["id"] for r in results})


def test_recommendations_corps_invalide_renvoie_422(client):
    """Un corps invalide (action manquante) est rejeté en 422 par pydantic."""
    resp = client.post("/api/recommendations", json={"swipes": [{"qid": "Q1"}]})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# POST /api/rooms/recommend — group_score
# --------------------------------------------------------------------------- #
def test_rooms_recommend(client, ctx):
    """2 membres -> picks de groupe non vides, triés, avec composantes."""
    genre_to_qids = ctx["genre_to_qids"]
    names = ctx["genre_names"]
    body = {
        "members": [
            {
                "user": "alice",
                "swipes": [
                    {"qid": q, "action": "superlike"} for q in genre_to_qids[names[0]][:3]
                ],
            },
            {
                "user": "bob",
                "swipes": [
                    {"qid": q, "action": "superlike"} for q in genre_to_qids[names[2]][:3]
                ],
            },
        ],
        "n": 5,
    }
    resp = client.post("/api/rooms/recommend", json=body)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert 0 < len(results) <= 5
    for p in results:
        assert set(p) >= {"id", "title", "group_score", "components"}
    scores = [p["group_score"] for p in results]
    assert scores == sorted(scores, reverse=True)


def test_rooms_recommend_veto_exclut(client, ctx):
    """Un veto d'un membre exclut le titre des picks de groupe."""
    genre_to_qids = ctx["genre_to_qids"]
    names = ctx["genre_names"]
    veto_target = genre_to_qids[names[3]][7]
    body = {
        "members": [
            {
                "user": "alice",
                "swipes": [
                    {"qid": q, "action": "superlike"} for q in genre_to_qids[names[0]][:3]
                ],
            },
            {
                "user": "bob",
                "swipes": (
                    [{"qid": q, "action": "superlike"} for q in genre_to_qids[names[2]][:3]]
                    + [{"qid": veto_target, "action": "veto"}]
                ),
            },
        ],
        "n": N_GENRES * PER_GENRE,
    }
    resp = client.post("/api/rooms/recommend", json=body)
    assert resp.status_code == 200
    assert veto_target not in {p["id"] for p in resp.json()["results"]}


# --------------------------------------------------------------------------- #
# GET /api/calibration
# --------------------------------------------------------------------------- #
def test_calibration(client):
    resp = client.get("/api/calibration", params={"n": 8})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 8
    for t in results:
        assert set(t) >= {"id", "title"}
        assert t["id"] and t["title"]


# --------------------------------------------------------------------------- #
# 503 — moteur non chargé (artefacts movreco absents)
# --------------------------------------------------------------------------- #
def test_503_si_moteur_non_charge(tmp_path):
    """Sans artefacts movreco, le moteur reste None et les endpoints rendent 503."""
    from movreco.config import load_config

    cfg = load_config()
    # data_dir vide -> aucun item/embedding -> SynergyEngine.load lève RuntimeError,
    # capturée par le lifespan : app.state.engine reste None.
    cfg["paths"] = {
        "data_dir": str(tmp_path / "vide"),
        "models_dir": str(tmp_path / "vide" / "models"),
    }
    app = create_app(cfg)
    with TestClient(app) as c:
        assert c.get("/api/provider-status").status_code == 503
        assert c.get("/api/catalog").status_code == 503
        assert c.post("/api/recommendations", json={"swipes": [], "n": 5}).status_code == 503
        assert c.post("/api/rooms/recommend", json={"members": [], "n": 5}).status_code == 503
        assert c.get("/api/calibration").status_code == 503
