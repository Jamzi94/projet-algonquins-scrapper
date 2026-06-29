"""Tests d'intégration de l'API FastAPI sur un catalogue synthétique.

Aucun réseau, aucun sentence-transformers : les embeddings sont synthétiques et
groupés par genre (cf. tests/_synthetic.py). On valide à la fois le CONTRAT D'API
(clés JSON, codes 404/422/503) et la PERTINENCE des recommandations (un goût pour
un genre -> des films du même genre en tête).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests._synthetic import build_synthetic_catalog  # noqa: E402


N_GENRES = 4
PER_GENRE = 15


@pytest.fixture()
def ctx(tmp_path):
    """Construit un catalogue synthétique en tmp_path et renvoie ses métadonnées."""
    return build_synthetic_catalog(
        tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE, dim=16, seed=0
    )


@pytest.fixture()
def client(ctx):
    """Client de test avec lifespan déclenché (chargement des artefacts)."""
    from movreco.api.app import create_app

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# /health
# --------------------------------------------------------------------------- #
def test_health_compte_les_artefacts(client, ctx):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    arts = body["artifacts"]
    assert arts["items"] == N_GENRES * PER_GENRE
    assert arts["embeddings"] is True
    assert arts["structured"] is True
    # Aucun modèle entraîné dans le catalogue synthétique.
    assert arts["model"] is False
    # rated.parquet présent (notes du propriétaire).
    assert arts["rated"] >= 1


# --------------------------------------------------------------------------- #
# /movies (recherche)
# --------------------------------------------------------------------------- #
def test_movies_recherche_insensible_casse(client):
    # "genre 2" en minuscules doit matcher "Genre 2 film i".
    resp = client.get("/movies", params={"q": "genre 2", "limit": 50})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == PER_GENRE
    for r in results:
        assert "Genre 2" in r["label"]
        # Clés du contrat.
        assert set(r.keys()) == {"qid", "label", "year", "genres"}
        assert isinstance(r["genres"], list)


def test_movies_sans_q_renvoie_premiers(client):
    resp = client.get("/movies", params={"limit": 5})
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 5


# --------------------------------------------------------------------------- #
# /movies/{qid}
# --------------------------------------------------------------------------- #
def test_movie_detail_200(client, ctx):
    qid = ctx["genre_to_qids"]["Genre 0"][0]
    resp = client.get(f"/movies/{qid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["qid"] == qid
    assert "Genre 0" in body["label"]
    assert set(body.keys()) == {
        "qid",
        "label",
        "year",
        "genres",
        "directors",
        "countries",
    }
    assert body["genres"] == ["Genre 0"]
    assert isinstance(body["directors"], list) and body["directors"]
    assert isinstance(body["countries"], list) and body["countries"]


def test_movie_detail_404(client):
    resp = client.get("/movies/QinconnuXYZ")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# /movies/{qid}/similar
# --------------------------------------------------------------------------- #
def test_similar_voisins_meme_genre_majoritaires(client, ctx):
    qid = ctx["genre_to_qids"]["Genre 1"][0]
    resp = client.get(f"/movies/{qid}/similar", params={"n": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"]["qid"] == qid
    results = body["results"]
    assert len(results) == 10
    # Le film lui-même est exclu.
    assert all(r["qid"] != qid for r in results)
    qid_to_genre = ctx["qid_to_genre"]
    same = sum(1 for r in results if qid_to_genre[r["qid"]] == "Genre 1")
    # Les voisins immédiats doivent appartenir au même genre (clusters distincts).
    assert same >= 0.6 * len(results)
    # Scores décroissants.
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_similar_404(client):
    resp = client.get("/movies/QinconnuXYZ/similar")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST /recommend (stateless)
# --------------------------------------------------------------------------- #
def test_post_recommend_pertinence_genre(client, ctx):
    # L'utilisateur note 3 films du genre 2 : le top-N doit être majoritairement
    # du genre 2 (VALIDATION DE PERTINENCE, pas seulement code 200).
    liked = ctx["genre_to_qids"]["Genre 2"][:3]
    payload = {
        "ratings": [{"qid": q, "rating": 5.0} for q in liked],
        "mode": "mvp",
        "n": 10,
    }
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "mvp"
    results = body["results"]
    assert len(results) == 10
    # Les films notés ne reviennent pas dans les recommandations.
    assert all(r["qid"] not in liked for r in results)
    qid_to_genre = ctx["qid_to_genre"]
    share = sum(1 for r in results if qid_to_genre[r["qid"]] == "Genre 2") / len(results)
    assert share >= 0.6
    for r in results:
        assert set(r.keys()) == {"qid", "label", "score"}


def test_post_recommend_ratings_vide_422(client):
    resp = client.post("/recommend", json={"ratings": [], "mode": "mvp", "n": 10})
    assert resp.status_code == 422


def test_post_recommend_aucun_qid_valide_422(client):
    resp = client.post(
        "/recommend",
        json={"ratings": [{"qid": "Qinexistant", "rating": 5.0}], "n": 10},
    )
    assert resp.status_code == 422


def test_post_recommend_hybrid_sans_modele_repli_mvp(client, ctx):
    # Aucun modèle entraîné -> repli mvp ; le champ mode reflète le mode réel.
    liked = ctx["genre_to_qids"]["Genre 0"][:3]
    payload = {
        "ratings": [{"qid": q, "rating": 5.0} for q in liked],
        "mode": "hybrid",
        "n": 10,
    }
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    assert resp.json()["mode"] == "mvp"


def test_post_recommend_exclude_respecte(client, ctx):
    liked = ctx["genre_to_qids"]["Genre 2"][:3]
    # On exclut explicitement quelques films du genre 2 non notés.
    excluded = ctx["genre_to_qids"]["Genre 2"][3:6]
    payload = {
        "ratings": [{"qid": q, "rating": 5.0} for q in liked],
        "mode": "mvp",
        "n": 10,
        "exclude": excluded,
    }
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    out_qids = {r["qid"] for r in resp.json()["results"]}
    assert out_qids.isdisjoint(set(excluded))


# --------------------------------------------------------------------------- #
# GET /recommend (notes persistées du propriétaire)
# --------------------------------------------------------------------------- #
def test_get_recommend_proprietaire_genre0_dominant(client, ctx):
    # Le propriétaire aime fortement le genre 0 (cf. rated.parquet synthétique).
    resp = client.get("/recommend", params={"mode": "hybrid", "n": 10})
    assert resp.status_code == 200
    body = resp.json()
    # Pas de modèle -> repli mvp.
    assert body["mode"] == "mvp"
    results = body["results"]
    assert len(results) == 10
    qid_to_genre = ctx["qid_to_genre"]
    share = sum(1 for r in results if qid_to_genre[r["qid"]] == "Genre 0") / len(results)
    assert share >= 0.6
    # Les films déjà notés par le propriétaire ne reviennent pas.
    assert all(r["qid"] not in set(ctx["owner_qids"]) for r in results)


# --------------------------------------------------------------------------- #
# Tolérance aux artefacts manquants -> 503
# --------------------------------------------------------------------------- #
def test_503_quand_embeddings_absents(tmp_path):
    # Catalogue sans embeddings : l'app démarre, mais /recommend renvoie 503.
    from movreco.api.app import create_app

    ctx = build_synthetic_catalog(tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE)
    emb_file = tmp_path / "processed" / "embeddings.npy"
    emb_file.unlink()

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        # /health démarre quand même.
        assert c.get("/health").status_code == 200
        # POST /recommend sans embeddings -> 503.
        liked = ctx["genre_to_qids"]["Genre 0"][:3]
        resp = c.post(
            "/recommend",
            json={"ratings": [{"qid": q, "rating": 5.0} for q in liked]},
        )
        assert resp.status_code == 503


def test_503_get_recommend_sans_rated(tmp_path):
    from movreco.api.app import create_app

    ctx = build_synthetic_catalog(tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE)
    (tmp_path / "processed" / "rated.parquet").unlink()

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        resp = c.get("/recommend")
        assert resp.status_code == 503
