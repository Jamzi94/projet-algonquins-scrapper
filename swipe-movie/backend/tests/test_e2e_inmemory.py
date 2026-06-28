"""Test e2e HORS-LIGNE du backend SwipeNight, en mémoire et en synergie movie-reco.

Ce test démarre l'app FastAPI RÉELLE (``server.app``) entièrement EN MÉMOIRE,
SANS réseau ni serveur MongoDB, puis déroule le parcours utilisateur complet sur
les VRAIES routes ``/api/...`` :

    register -> login -> me -> onboarding (préférences + swipes/like) ->
    recommandations (home + reco par contexte) -> room (création, vote, résultat)
    -> provider-status.

CONTRAT D'ENVIRONNEMENT (fixé AVANT l'import de ``server``)
-----------------------------------------------------------
- ``MONGO_URL=memory``      -> Mongo EN MÉMOIRE via mongomock-motor (database.py).
- ``CATALOG_SOURCE=movreco``-> catalogue Wikidata via le pont recommender_bridge.
- ``RECO_VIA_BRIDGE=1``     -> les endpoints de reco délèguent au moteur movreco.
- ``JWT_SECRET=test``       -> secret JWT déterministe pour l'auth.
- TMDB reste désactivé (aucune clé) : le test n'a besoin d'AUCUN réseau.

Prérequis & skips PROPRES : si ``mongomock_motor`` ou ``movreco`` ne sont pas
installés, ou si le catalogue movreco
(``movie-reco/data/processed/items.parquet``) est absent, le module est sauté
sans casser la collecte pytest.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# 1) Environnement IMPÉRATIVEMENT fixé AVANT tout import de ``server`` :
#    database.py / auth.py / licensing.py lisent ces variables à l'import.
# --------------------------------------------------------------------------- #
os.environ["MONGO_URL"] = "memory"          # Mongo en mémoire (mongomock-motor)
os.environ["CATALOG_SOURCE"] = "movreco"    # catalogue Wikidata via le pont
os.environ["RECO_VIA_BRIDGE"] = "1"         # reco déléguée au moteur movreco
os.environ["JWT_SECRET"] = "test"           # secret JWT déterministe
# TMDB désactivé : aucune clé -> can_use_tmdb() == False (pas de réseau).
os.environ.pop("TMDB_API_KEY", None)
os.environ["EXTERNAL_APIS_ENABLED"] = "false"

# --------------------------------------------------------------------------- #
# 2) Chemins d'import : backend (server/recommender_bridge), movie-reco (movreco).
#    Fichier : backend/tests/test_e2e_inmemory.py
#    parents[1] -> backend ; parents[2] -> swipe-movie ; parents[3] -> racine.
# --------------------------------------------------------------------------- #
_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MOVRECO_ROOT = _REPO_ROOT / "movie-reco"
for _p in (str(_BACKEND), str(_MOVRECO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# --------------------------------------------------------------------------- #
# 3) Skips propres : dépendances mémoire + moteur movreco + artefacts catalogue.
# --------------------------------------------------------------------------- #
pytest.importorskip("mongomock_motor")
pytest.importorskip("fastapi")
pytest.importorskip("movreco")

_ITEMS_PARQUET = _MOVRECO_ROOT / "data" / "processed" / "items.parquet"
if not _ITEMS_PARQUET.exists():
    pytest.skip(
        "Catalogue movreco absent (%s) : test e2e en mémoire ignoré." % _ITEMS_PARQUET,
        allow_module_level=True,
    )

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    """Démarre l'app en mémoire. ``with TestClient`` déclenche startup/shutdown.

    Le hook startup amorce le catalogue (movreco via le pont) et le feature
    store. On vérifie au passage que le pont est bien actif et que le catalogue
    n'est pas vide, sinon le test n'aurait aucun sens : on saute proprement.
    """
    with TestClient(server.app) as c:
        if not server.CONTENTS:
            pytest.skip("Catalogue vide après startup : pont movreco indisponible.")
        if not server.bridge_active():
            pytest.skip("Pont movreco inactif après startup (artefacts manquants ?).")
        yield c


@pytest.fixture(scope="module")
def creds():
    suffix = uuid.uuid4().hex[:8]
    return {
        "email": f"e2e_{suffix}@swipenight.app",
        "username": f"e2e_{suffix}",
        "password": "password123",
        "display_name": f"E2E {suffix}",
    }


def test_e2e_full_journey_inmemory(client, creds):
    """Parcours réel bout-en-bout sur les VRAIES routes, 100 % hors-ligne."""

    # --- (0) Le backend tourne en mémoire avec le catalogue movreco. ---------
    assert len(server.CONTENTS) > 0
    assert server.bridge_active() is True

    # --- (1) register -> token + user ---------------------------------------
    r = client.post("/api/auth/register", json=creds)
    assert r.status_code == 200, r.text
    reg = r.json()
    assert "token" in reg and "user" in reg
    assert reg["user"]["email"] == creds["email"].lower()
    assert reg["user"]["preferences"]["onboarded"] is False
    token = reg["token"]
    headers = _auth(token)

    # register en double -> 400 (email déjà pris)
    assert client.post("/api/auth/register", json=creds).status_code == 400

    # --- (2) login -----------------------------------------------------------
    r = client.post("/api/auth/login",
                    json={"email": creds["email"], "password": creds["password"]})
    assert r.status_code == 200, r.text
    assert "token" in r.json()
    # mauvais mot de passe -> 401
    assert client.post(
        "/api/auth/login",
        json={"email": creds["email"], "password": "wrong"}).status_code == 401

    # --- (3) me (auth + non-auth) -------------------------------------------
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == creds["email"].lower()
    assert r.json()["username"] == creds["username"]
    # sans token -> 401/403
    assert client.get("/api/auth/me").status_code in (401, 403)

    # --- (4) onboarding : préférences puis quelques likes -------------------
    prefs_body = {
        "country": "FR",
        "platforms": [],
        "formats": ["movies"],
        "genres": ["Science fiction", "Thriller"],
        "moods": ["dark"],
        "onboarded": True,
    }
    r = client.put("/api/users/preferences", json=prefs_body, headers=headers)
    assert r.status_code == 200, r.text
    prefs = r.json()["preferences"]
    assert prefs["onboarded"] is True
    assert prefs["country"] == "FR"

    # On pioche des contenus RÉELS du catalogue via la vraie route /api/contents
    browse = client.get("/api/contents", headers=headers)
    assert browse.status_code == 200, browse.text
    bdata = browse.json()
    assert bdata["count"] > 0
    assert len(bdata["results"]) > 0
    content_ids = [c["id"] for c in bdata["results"][:3]]
    assert content_ids, "le catalogue doit exposer au moins 3 contenus"

    # quelques events "like" (swipes) sur ces contenus
    for cid in content_ids:
        r = client.post("/api/events",
                        json={"content_id": cid, "event_type": "like"},
                        headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    # l'état a bien été persisté en mémoire (seen_liked)
    detail = client.get(f"/api/contents/{content_ids[0]}", headers=headers).json()
    assert detail["user_state"] is not None
    assert detail["user_state"]["state"] == "seen_liked"
    # le détail expose la forme attendue (score + raisons + reviews)
    assert detail["content"]["id"] == content_ids[0]
    assert isinstance(detail["match_score"], int)
    assert isinstance(detail["reasons"], list)
    assert "reviews" in detail and "community_rating" in detail

    # --- (5) recommandations : par contexte + home --------------------------
    r = client.get("/api/recommendations?context=general&limit=10", headers=headers)
    assert r.status_code == 200, r.text
    reco = r.json()
    assert reco["context"] == "general"
    assert isinstance(reco["results"], list)
    assert len(reco["results"]) > 0, "les recommandations ne doivent pas être vides"
    first = reco["results"][0]
    # forme correcte d'un item de reco
    assert "content" in first and "match_score" in first and "reasons" in first
    assert first["content"].get("id")
    assert 1 <= first["match_score"] <= 99
    assert isinstance(first["reasons"], list)
    # les recos ne doivent pas inclure de doublons
    rec_ids = [item["content"]["id"] for item in reco["results"]]
    assert len(rec_ids) == len(set(rec_ids))

    # home feed : hero + au moins un rail non vide
    r = client.get("/api/recommendations/home", headers=headers)
    assert r.status_code == 200, r.text
    home = r.json()
    assert "hero" in home and "rails" in home
    assert len(home["rails"]) >= 1
    assert home["hero"] is not None
    assert "match_score" in home["hero"]
    assert "reasons" in home["hero"]
    assert home["hero"]["content"].get("id")
    for rail in home["rails"]:
        assert "title" in rail and "context" in rail and "items" in rail
        assert len(rail["items"]) > 0

    # --- (6) room : création, démarrage, vote, vérif logique de quorum ------
    # quorum=1 + seuil 50 % : un seul superlike suffit à désigner un gagnant.
    room_body = {"name": "E2E Night", "threshold_percent": 50, "quorum": 1,
                 "max_users": 5, "filters": {}}
    r = client.post("/api/rooms", json=room_body, headers=headers)
    assert r.status_code == 200, r.text
    room = r.json()
    rid = room["id"]
    assert len(room["join_code"]) == 6
    assert room["status"] == "lobby"

    # démarrage (propriétaire) -> des candidats sont générés
    r = client.post(f"/api/rooms/{rid}/start", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] > 0

    # liste des candidats
    r = client.get(f"/api/rooms/{rid}/candidates", headers=headers)
    assert r.status_code == 200, r.text
    cands = r.json()["results"]
    assert len(cands) > 0
    first_cid = cands[0]["content"]["id"]

    # avant tout vote : aucun gagnant
    pre = client.get(f"/api/rooms/{rid}/result", headers=headers).json()
    assert pre["winner"] is None

    # vote superlike -> avec quorum=1 et seuil 50 %, ce contenu gagne
    r = client.post(f"/api/rooms/{rid}/vote",
                    json={"content_id": first_cid, "vote": "superlike"},
                    headers=headers)
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["winner"] is not None
    assert summary["winner"]["content_id"] == first_cid
    assert summary["quorum"] == 1

    # le résultat confirme le gagnant (logique d'accord/seuil)
    res = client.get(f"/api/rooms/{rid}/result", headers=headers).json()
    assert res["winner"] is not None
    assert res["winner"]["content_id"] == first_cid
    assert res["winner"]["agreement_rate"] >= 0.5

    # relance -> tour suivant
    rl = client.post(f"/api/rooms/{rid}/relaunch",
                     json={"threshold_percent": 50}, headers=headers)
    assert rl.status_code == 200, rl.text
    assert rl.json()["round"] == 2

    # --- (7) provider-status : cohérence des toggles de synergie ------------
    r = client.get("/api/provider-status")
    assert r.status_code == 200, r.text
    ps = r.json()
    # TMDB désactivé (pas de clé) ET cohérent avec can_use_tmdb()
    assert ps["tmdb_enabled"] is False
    assert ps["tmdb_key_present"] is False
    # source de catalogue = movreco (synergie movie-reco) + reco via le pont
    assert ps["catalog_source"] == "movreco"
    assert ps["reco_via_bridge"] is True
