"""SwipeNight API integration tests (pytest).

Covers: auth, preferences, calibration, browse, content detail,
recommendations, events/state, watchlist, reviews, rooms full flow, privacy.
Uses the public preview URL exposed via EXPO_PUBLIC_BACKEND_URL.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
# Test d'intégration live-server : nécessite RÉSEAU + MongoDB + un backend lancé,
# accessible via EXPO_PUBLIC_BACKEND_URL. En l'absence de cette variable (ex.
# environnement hors-ligne), on saute le module entier au lieu d'interrompre la
# collecte pytest (skip au niveau module plutôt qu'assert qui casse tout).
if not BASE_URL:
    pytest.skip(
        "EXPO_PUBLIC_BACKEND_URL non défini : test d'intégration live-server "
        "ignoré (prérequis RÉSEAU + MongoDB + backend lancé).",
        allow_module_level=True,
    )
API = f"{BASE_URL}/api"

SEEDED_EMAIL = "alex_noir@swipenight.app"
SEEDED_PASSWORD = "password123"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def seeded_token(session):
    r = session.post(f"{API}/auth/login",
                     json={"email": SEEDED_EMAIL, "password": SEEDED_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def seeded_auth_headers(seeded_token):
    return {"Authorization": f"Bearer {seeded_token}"}


@pytest.fixture(scope="session")
def new_user_creds():
    suffix = uuid.uuid4().hex[:8]
    return {
        "email": f"TEST_{suffix}@swipenight.app",
        "password": "password123",
        "username": f"TEST_{suffix}",
        "display_name": f"Tester {suffix}",
    }


@pytest.fixture(scope="session")
def new_user_token(session, new_user_creds):
    r = session.post(f"{API}/auth/register", json=new_user_creds)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def new_user_headers(new_user_token):
    return {"Authorization": f"Bearer {new_user_token}"}


# ---------- auth ----------
class TestAuth:
    def test_login_seeded_user(self, session):
        r = session.post(f"{API}/auth/login",
                         json={"email": SEEDED_EMAIL, "password": SEEDED_PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and "user" in data
        assert data["user"]["email"] == SEEDED_EMAIL
        assert data["user"]["preferences"]["onboarded"] is True

    def test_login_invalid_password(self, session):
        r = session.post(f"{API}/auth/login",
                         json={"email": SEEDED_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_register_new_user(self, new_user_token, new_user_creds):
        assert new_user_token  # registered in fixture

    def test_register_duplicate_email(self, session, new_user_creds):
        r = session.post(f"{API}/auth/register", json=new_user_creds)
        assert r.status_code == 400

    def test_me_authenticated(self, session, seeded_auth_headers):
        r = session.get(f"{API}/auth/me", headers=seeded_auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == SEEDED_EMAIL

    def test_me_unauthenticated(self, session):
        r = session.get(f"{API}/auth/me")
        assert r.status_code in (401, 403)


# ---------- onboarding ----------
class TestOnboarding:
    def test_update_preferences(self, session, new_user_headers):
        body = {
            "country": "US", "platforms": ["Netflix"], "formats": ["movies"],
            "genres": ["Thriller", "Sci-Fi"], "moods": ["dark"], "onboarded": True,
        }
        r = session.put(f"{API}/users/preferences", json=body,
                        headers=new_user_headers)
        assert r.status_code == 200
        prefs = r.json()["preferences"]
        assert prefs["onboarded"] is True
        assert "Thriller" in prefs["genres"]

    def test_calibration_returns_20(self, session, new_user_headers):
        r = session.get(f"{API}/contents/calibration",
                        headers=new_user_headers)
        assert r.status_code == 200
        results = r.json()["results"]
        assert 15 <= len(results) <= 20


# ---------- recommendations ----------
class TestRecommendations:
    def test_home_feed(self, session, seeded_auth_headers):
        r = session.get(f"{API}/recommendations/home",
                        headers=seeded_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "hero" in data and "rails" in data
        assert len(data["rails"]) >= 1
        assert data["hero"] is not None
        assert "match_score" in data["hero"]
        assert "reasons" in data["hero"]

    @pytest.mark.parametrize("ctx", ["general", "movies", "series", "anime", "new"])
    def test_recommendations_contexts(self, session, seeded_auth_headers, ctx):
        r = session.get(f"{API}/recommendations?context={ctx}",
                        headers=seeded_auth_headers)
        assert r.status_code == 200
        assert "results" in r.json()

    def test_reasons_endpoint(self, session, seeded_auth_headers):
        home = session.get(f"{API}/recommendations/home",
                           headers=seeded_auth_headers).json()
        cid = home["hero"]["content"]["id"]
        r = session.get(f"{API}/recommendations/{cid}/reasons",
                        headers=seeded_auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json()["reasons"], list)


# ---------- browse + content detail ----------
class TestBrowse:
    def test_browse_no_filters(self, session, seeded_auth_headers):
        r = session.get(f"{API}/contents", headers=seeded_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 100
        assert len(data["results"]) > 0

    def test_browse_type_movie(self, session, seeded_auth_headers):
        r = session.get(f"{API}/contents?type=movie",
                        headers=seeded_auth_headers)
        assert r.status_code == 200
        for c in r.json()["results"][:10]:
            assert c["type"] == "movie"

    def test_browse_search(self, session, seeded_auth_headers):
        # generic single-letter search should match many titles
        r = session.get(f"{API}/contents?q=a", headers=seeded_auth_headers)
        assert r.status_code == 200
        assert r.json()["count"] > 0

    def test_content_detail(self, session, seeded_auth_headers):
        b = session.get(f"{API}/contents", headers=seeded_auth_headers).json()
        cid = b["results"][0]["id"]
        r = session.get(f"{API}/contents/{cid}", headers=seeded_auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["content"]["id"] == cid
        assert "match_score" in d
        assert "reasons" in d
        assert "reviews" in d
        assert "community_rating" in d


# ---------- events / state / watchlist ----------
class TestEventsAndWatchlist:
    def test_event_like_persists_state(self, session, seeded_auth_headers):
        b = session.get(f"{API}/contents", headers=seeded_auth_headers).json()
        cid = b["results"][0]["id"]
        r = session.post(f"{API}/events", headers=seeded_auth_headers,
                         json={"content_id": cid, "event_type": "like"})
        assert r.status_code == 200
        d = session.get(f"{API}/contents/{cid}",
                        headers=seeded_auth_headers).json()
        assert d["user_state"]["state"] == "seen_liked"

    def test_watchlist_add_and_get(self, session, new_user_headers):
        b = session.get(f"{API}/contents", headers=new_user_headers).json()
        cid = b["results"][0]["id"]
        r = session.post(f"{API}/watchlist/{cid}", headers=new_user_headers)
        assert r.status_code == 200
        wl = session.get(f"{API}/watchlist", headers=new_user_headers).json()
        assert any(c["id"] == cid for c in wl["results"])

    def test_watchlist_remove(self, session, new_user_headers):
        b = session.get(f"{API}/contents", headers=new_user_headers).json()
        cid = b["results"][1]["id"]
        session.post(f"{API}/watchlist/{cid}", headers=new_user_headers)
        r = session.delete(f"{API}/watchlist/{cid}", headers=new_user_headers)
        assert r.status_code == 200
        wl = session.get(f"{API}/watchlist", headers=new_user_headers).json()
        assert not any(c["id"] == cid for c in wl["results"])


# ---------- reviews ----------
class TestReviews:
    def test_create_review(self, session, new_user_headers):
        b = session.get(f"{API}/contents", headers=new_user_headers).json()
        cid = b["results"][2]["id"]
        r = session.post(f"{API}/reviews", headers=new_user_headers, json={
            "content_id": cid, "rating": 4.5, "reaction": "loved",
            "body": "TEST review", "visibility": "public"})
        assert r.status_code == 200
        rev = r.json()
        assert rev["content_id"] == cid
        # public review should appear
        lr = session.get(f"{API}/contents/{cid}/reviews",
                         headers=new_user_headers)
        assert lr.status_code == 200
        assert any(rr["body"] == "TEST review" for rr in lr.json()["results"])

    def test_private_review_not_visible_to_others(self, session, new_user_headers,
                                                  seeded_auth_headers):
        b = session.get(f"{API}/contents", headers=new_user_headers).json()
        cid = b["results"][3]["id"]
        session.post(f"{API}/reviews", headers=new_user_headers, json={
            "content_id": cid, "rating": 1.5, "body": "TEST private",
            "visibility": "private"})
        lr = session.get(f"{API}/contents/{cid}/reviews",
                        headers=seeded_auth_headers).json()
        assert not any(rr.get("body") == "TEST private"
                       for rr in lr["results"])


# ---------- rooms ----------
class TestRooms:
    def test_join_demo_room(self, session, new_user_headers):
        r = session.post(f"{API}/rooms/join", headers=new_user_headers,
                         json={"join_code": "MOVIE1"})
        assert r.status_code == 200
        assert r.json()["join_code"] == "MOVIE1"

    def test_full_room_flow(self, session, new_user_headers):
        # create a solo room with quorum=1 + low threshold for deterministic winner
        c = session.post(f"{API}/rooms", headers=new_user_headers, json={
            "name": "TEST_room", "threshold_percent": 50, "quorum": 1,
            "max_users": 5, "filters": {}})
        assert c.status_code == 200
        room = c.json()
        rid, code = room["id"], room["join_code"]
        assert len(code) == 6

        # start (owner)
        s = session.post(f"{API}/rooms/{rid}/start", headers=new_user_headers)
        assert s.status_code == 200
        assert s.json()["candidates"] > 0

        # candidates
        cand = session.get(f"{API}/rooms/{rid}/candidates",
                           headers=new_user_headers)
        assert cand.status_code == 200
        cands = cand.json()["results"]
        assert len(cands) > 0
        first_cid = cands[0]["content"]["id"]

        # vote superlike
        v = session.post(f"{API}/rooms/{rid}/vote", headers=new_user_headers,
                        json={"content_id": first_cid, "vote": "superlike"})
        assert v.status_code == 200

        # result
        res = session.get(f"{API}/rooms/{rid}/result",
                          headers=new_user_headers).json()
        assert res["winner"] is not None
        assert res["winner"]["content_id"] == first_cid

        # relaunch
        rl = session.post(f"{API}/rooms/{rid}/relaunch",
                          headers=new_user_headers,
                          json={"threshold_percent": 50})
        assert rl.status_code == 200
        assert rl.json()["round"] == 2

    def test_join_invalid_code(self, session, new_user_headers):
        r = session.post(f"{API}/rooms/join", headers=new_user_headers,
                         json={"join_code": "ZZZZZZ"})
        assert r.status_code == 404


# ---------- privacy ----------
class TestPrivacy:
    def test_get_privacy_defaults(self, session, new_user_headers):
        r = session.get(f"{API}/users/me/privacy", headers=new_user_headers)
        assert r.status_code == 200
        d = r.json()
        # newly created user defaults are private
        assert d.get("history_visibility") == "private"

    def test_update_privacy(self, session, new_user_headers):
        r = session.put(f"{API}/users/me/privacy", headers=new_user_headers,
                        json={"history_visibility": "friends"})
        assert r.status_code == 200
        assert r.json()["history_visibility"] == "friends"


# ---------- dev daily job ----------
class TestDevJob:
    def test_run_daily_job(self, session):
        r = session.post(f"{API}/dev/run-daily-job", timeout=120)
        assert r.status_code == 200
        assert r.json()["ok"] is True
