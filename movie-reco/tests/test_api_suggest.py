"""Tests d'intégration de l'endpoint GET /suggest (apprentissage actif).

Aucun réseau, aucun sentence-transformers : catalogue synthétique groupé par
genre (cf. tests/_synthetic.py). On valide le CONTRAT D'API de /suggest (clés
JSON, longueur, exclusion des notés) ET la COUVERTURE (les suggestions touchent
plusieurs genres, signe d'une exploration de l'espace).
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
    return build_synthetic_catalog(
        tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE, dim=16, seed=0
    )


@pytest.fixture()
def client(ctx):
    from movreco.api.app import create_app

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# Contrat d'API
# --------------------------------------------------------------------------- #
def test_suggest_renvoie_n_films(client):
    resp = client.get("/suggest", params={"n": 5})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 5
    for r in results:
        # Clés exactes du contrat : qid + label (pas de score).
        assert set(r.keys()) == {"qid", "label"}
        assert isinstance(r["qid"], str) and r["qid"]
        assert isinstance(r["label"], str) and r["label"]


def test_suggest_defaut_n_dix(client):
    resp = client.get("/suggest")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 10


def test_suggest_exclut_les_notes_du_proprietaire(client, ctx):
    # Le propriétaire a déjà noté owner_qids : ils ne doivent pas être proposés.
    resp = client.get("/suggest", params={"n": N_GENRES * PER_GENRE})
    assert resp.status_code == 200
    out_qids = {r["qid"] for r in resp.json()["results"]}
    owner = set(ctx["owner_qids"])
    assert out_qids.isdisjoint(owner)


def test_suggest_sans_doublon(client):
    resp = client.get("/suggest", params={"n": 12})
    qids = [r["qid"] for r in resp.json()["results"]]
    assert len(qids) == len(set(qids))


def test_suggest_deterministe(client):
    a = client.get("/suggest", params={"n": 8}).json()["results"]
    b = client.get("/suggest", params={"n": 8}).json()["results"]
    assert [r["qid"] for r in a] == [r["qid"] for r in b]


def test_suggest_couvre_plusieurs_genres(client, ctx):
    """L'apprentissage actif explore : les suggestions touchent >1 genre."""
    resp = client.get("/suggest", params={"n": N_GENRES})
    results = resp.json()["results"]
    qid_to_genre = ctx["qid_to_genre"]
    genres = {qid_to_genre[r["qid"]] for r in results}
    # Avec un farthest-point sur 4 clusters distincts, on attend une bonne
    # couverture (au moins deux genres représentés).
    assert len(genres) >= 2


def test_suggest_n_borne_par_le_catalogue(client):
    """Demander plus que le catalogue ne donne pas plus de films non notés."""
    total = N_GENRES * PER_GENRE
    resp = client.get("/suggest", params={"n": total + 50})
    assert resp.status_code == 200
    results = resp.json()["results"]
    # Au plus (total - nb de notés) suggestions.
    assert len(results) <= total


def test_suggest_n_invalide_422(client):
    # n < 1 rejeté par la validation FastAPI (ge=1).
    resp = client.get("/suggest", params={"n": 0})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Tolérance aux artefacts manquants -> 503
# --------------------------------------------------------------------------- #
def test_suggest_503_sans_embeddings(tmp_path):
    from movreco.api.app import create_app

    ctx = build_synthetic_catalog(tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE)
    (tmp_path / "processed" / "embeddings.npy").unlink()

    app = create_app(ctx["cfg"])
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/suggest").status_code == 503
