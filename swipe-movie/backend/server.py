"""SwipeNight API — FastAPI + MongoDB + WebSocket rooms + hybrid recommender."""
import logging
import os
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (APIRouter, Depends, FastAPI, HTTPException, WebSocket,
                     WebSocketDisconnect)
from pydantic import BaseModel, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

import recommender as R
from auth import (create_access_token, get_current_user, hash_password,
                  verify_password)
from database import client, db
from seed_data import build_catalog
from licensing import get_provider_status, tmdb_disabled_reason
from services.external import tmdb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("swipenight")

app = FastAPI(title="SwipeNight API")
api = APIRouter(prefix="/api")

# In-memory feature store (rebuilt on startup / reseed)
CONTENTS: dict = {}          # id -> content
CONTENT_VECTORS: dict = {}   # id -> vector

CURRENT_YEAR = datetime.now().year


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_dt(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)


# ===========================================================================
# Models (request bodies)
# ===========================================================================
class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    username: str
    display_name: str | None = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class PreferencesBody(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    country: str | None = None
    platforms: list[str] | None = None
    formats: list[str] | None = None
    genres: list[str] | None = None
    moods: list[str] | None = None
    onboarded: bool | None = None


class EventBody(BaseModel):
    content_id: str
    event_type: str  # like, dislike, superlike, veto, neutral, watchlist, abandoned, rating
    event_value: float | None = None
    source: str = "app"


class StateBody(BaseModel):
    state: str | None = None
    rating: float | None = None
    reaction: str | None = None
    is_excluded_from_reco: bool | None = None


class ReviewBody(BaseModel):
    content_id: str
    rating: float | None = None
    reaction: str | None = None
    body: str | None = None
    is_spoiler: bool = False
    visibility: str = "public"  # private / friends / public


class PrivacyBody(BaseModel):
    history_visibility: str | None = None
    ratings_visibility: str | None = None
    watchlist_visibility: str | None = None
    profile_visibility: str | None = None


class RoomFiltersBody(BaseModel):
    formats: list[str] = []
    genres: list[str] = []
    platforms: list[str] = []
    country: str | None = None
    min_year: int | None = None
    max_year: int | None = None
    min_rating: float | None = None
    max_runtime: int | None = None
    languages: list[str] = []
    allow_seen_by_some: bool = True
    allow_seen_by_all: bool = False


class RoomCreateBody(BaseModel):
    name: str
    threshold_percent: int = 60
    quorum: int = 2
    max_users: int = 5
    filters: RoomFiltersBody = RoomFiltersBody()


class JoinBody(BaseModel):
    join_code: str


class VoteBody(BaseModel):
    content_id: str
    vote: str  # superlike, like, neutral, dislike, veto


class RelaunchBody(BaseModel):
    threshold_percent: int | None = None
    filters: RoomFiltersBody | None = None


# ===========================================================================
# Feature store helpers
# ===========================================================================
async def load_feature_store():
    CONTENTS.clear()
    CONTENT_VECTORS.clear()
    docs = await db.contents.find({}, {"_id": 0}).to_list(5000)
    for c in docs:
        CONTENTS[c["id"]] = c
        CONTENT_VECTORS[c["id"]] = R.build_content_vector(c)
    logger.info("Feature store loaded: %d contents", len(CONTENTS))


async def get_user_states(user_id):
    return await db.user_content_states.find(
        {"user_id": user_id}, {"_id": 0}).to_list(2000)


def signal_from_state(state, rating):
    s = R.STATE_SIGNAL.get(state, 0)
    if rating is not None:
        if rating >= 4.5:
            s += 5
        elif rating >= 3.5:
            s += 3
        elif rating <= 2:
            s -= 3
    return s


async def build_user_context(user, states=None):
    if states is None:
        states = await get_user_states(user["id"])
    prefs = user.get("preferences", {}) or {}
    state_map, excluded = {}, set()
    interactions, neg_genres, liked_titles = [], {}, []
    has_taste = False
    liked_anime = False
    for st in states:
        cid = st["content_id"]
        state_map[cid] = st.get("state")
        if st.get("is_excluded_from_reco") or st.get("state") == "excluded_from_recommendations":
            excluded.add(cid)
        sig = signal_from_state(st.get("state"), st.get("rating"))
        if sig != 0:
            interactions.append({"content_id": cid, "signal": sig,
                                 "ts": parse_dt(st.get("updated_at", now_iso()))})
        if sig > 0:
            has_taste = True
            c = CONTENTS.get(cid)
            if c:
                liked_titles.append({"title": c["title"], "genres": c.get("genres", []),
                                     "cast": c.get("cast", []), "crew": c.get("crew", [])})
                if c.get("type") == "anime":
                    liked_anime = True
        if sig < 0:
            c = CONTENTS.get(cid)
            if c:
                for g in c.get("genres", []):
                    neg_genres[g.lower()] = neg_genres.get(g.lower(), 0) + 1
    rejected = {g for g, n in neg_genres.items() if n >= 2}
    user_vector = R.build_user_vector(interactions, CONTENT_VECTORS)
    return {
        "user_vector": user_vector,
        "platforms": prefs.get("platforms", []),
        "country": prefs.get("country", "US"),
        "moods": prefs.get("moods", []),
        "formats": prefs.get("formats", []),
        "preferred_genres": prefs.get("genres", []),
        "rejected_genres": rejected,
        "state_map": state_map,
        "excluded": excluded,
        "has_taste": has_taste,
        "anime_affinity": ("anime" in prefs.get("formats", [])) or liked_anime,
        "liked_titles": liked_titles,
    }


def rank_for_context(ctx, context_key, limit):
    contents = list(CONTENTS.values())
    # context-specific candidate filtering
    if context_key in ("movies", "series", "anime"):
        contents = [c for c in contents if c["type"] == context_key]
    elif context_key == "platforms":
        plats = set(ctx.get("platforms") or [])
        contents = [c for c in contents if set(c.get("providers", [])) & plats]
    elif context_key == "new":
        contents = [c for c in contents if (c.get("year") or 0) >= CURRENT_YEAR - 2]

    cands = R.generate_candidates(contents, ctx)
    scored = []
    for c in cands:
        s, comp = R.score_content(c, CONTENT_VECTORS[c["id"]], ctx["user_vector"], ctx)
        scored.append((c, s, comp))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[: max(limit * 2, 40)]
    reranked = R.mmr_rerank([(c, s) for c, s, _ in top], CONTENT_VECTORS, limit)
    score_map = {c["id"]: (s, comp) for c, s, comp in scored}
    out = []
    for c in reranked:
        s, comp = score_map[c["id"]]
        match = max(1, min(99, round(s * 100)))
        out.append({
            "content": public_content(c),
            "match_score": match,
            "components": comp,
            "reasons": R.generate_explanations(c, ctx),
        })
    return out


def public_content(c):
    """Trim a content doc for list payloads."""
    return {k: c.get(k) for k in (
        "id", "type", "title", "original_title", "year", "overview",
        "poster_url", "backdrop_url", "runtime", "genres", "providers",
        "external_rating", "popularity", "metadata_source", "image_source",
        "external_ids")}


# ===========================================================================
# Auth
# ===========================================================================
@api.post("/auth/register")
async def register(body: RegisterBody):
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(400, "Email already registered")
    if await db.users.find_one({"username": body.username}):
        raise HTTPException(400, "Username already taken")
    uid = str(uuid.uuid4())
    user = {
        "id": uid,
        "email": body.email.lower(),
        "username": body.username,
        "display_name": body.display_name or body.username,
        "avatar_url": None,
        "is_anonymous": False,
        "hashed_password": hash_password(body.password),
        "preferences": {"onboarded": False, "platforms": [], "formats": [],
                        "genres": [], "moods": [], "country": "US"},
        "created_at": now_iso(),
        "deleted_at": None,
    }
    await db.users.insert_one(user)
    await db.user_privacy_settings.insert_one({
        "user_id": uid, "history_visibility": "private",
        "ratings_visibility": "private", "watchlist_visibility": "private",
        "profile_visibility": "friends"})
    token = create_access_token(uid, body.username)
    return {"token": token, "user": sanitize_user(user)}


@api.post("/auth/login")
async def login(body: LoginBody):
    user = await db.users.find_one({"email": body.email.lower(), "deleted_at": None})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(user["id"], user["username"])
    return {"token": token, "user": sanitize_user(user)}


def sanitize_user(u):
    return {k: u.get(k) for k in (
        "id", "email", "username", "display_name", "avatar_url",
        "is_anonymous", "preferences", "created_at")}


@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return sanitize_user(user)


@api.put("/users/preferences")
async def update_prefs(body: PreferencesBody, user=Depends(get_current_user)):
    prefs = user.get("preferences", {}) or {}
    upd = {}
    for f in ("country", "platforms", "formats", "genres", "moods", "onboarded"):
        v = getattr(body, f)
        if v is not None:
            prefs[f] = v
    upd["preferences"] = prefs
    if body.display_name is not None:
        upd["display_name"] = body.display_name
    if body.avatar_url is not None:
        upd["avatar_url"] = body.avatar_url
    await db.users.update_one({"id": user["id"]}, {"$set": upd})
    user = await db.users.find_one({"id": user["id"]})
    # taste vector recompute (event-driven)
    await recompute_user_vector(user["id"])
    return sanitize_user(user)


@api.get("/users/me/profile")
async def my_profile(user=Depends(get_current_user)):
    states = await get_user_states(user["id"])
    counts = {}
    for s in states:
        counts[s.get("state")] = counts.get(s.get("state"), 0) + 1
    reviews = await db.reviews.count_documents({"user_id": user["id"], "deleted_at": None})
    return {"user": sanitize_user(user), "state_counts": counts,
            "reviews": reviews, "total_rated": sum(1 for s in states if s.get("rating"))}


@api.get("/users/me/privacy")
async def get_privacy(user=Depends(get_current_user)):
    p = await db.user_privacy_settings.find_one({"user_id": user["id"]}, {"_id": 0})
    return p or {}


@api.put("/users/me/privacy")
async def set_privacy(body: PrivacyBody, user=Depends(get_current_user)):
    upd = {k: v for k, v in body.dict().items() if v is not None}
    await db.user_privacy_settings.update_one(
        {"user_id": user["id"]}, {"$set": upd}, upsert=True)
    return await db.user_privacy_settings.find_one({"user_id": user["id"]}, {"_id": 0})


@api.delete("/users/me/history")
async def delete_history(user=Depends(get_current_user)):
    await db.user_content_states.delete_many({"user_id": user["id"]})
    await db.user_events.delete_many({"user_id": user["id"]})
    await recompute_user_vector(user["id"])
    return {"ok": True}


@api.delete("/users/me")
async def delete_account(user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"deleted_at": now_iso()}})
    await db.user_content_states.delete_many({"user_id": user["id"]})
    await db.user_events.delete_many({"user_id": user["id"]})
    await db.reviews.update_many({"user_id": user["id"]}, {"$set": {"deleted_at": now_iso()}})
    return {"ok": True}


# ===========================================================================
# Content / browse
# ===========================================================================
@api.get("/contents")
async def browse(q: str = "", type: str = "", genre: str = "", platform: str = "",
                 sort: str = "recommended", min_rating: float = 0,
                 max_runtime: int = 0, min_year: int = 0, max_year: int = 0,
                 user=Depends(get_current_user)):
    items = list(CONTENTS.values())
    if q:
        ql = q.lower()
        items = [c for c in items if ql in c["title"].lower()
                 or ql in (c.get("original_title", "").lower())]
    if type:
        items = [c for c in items if c["type"] == type]
    if genre:
        items = [c for c in items if genre.lower() in [g.lower() for g in c.get("genres", [])]]
    if platform:
        items = [c for c in items if platform in c.get("providers", [])]
    if min_rating:
        items = [c for c in items if (c.get("external_rating") or 0) >= min_rating]
    if max_runtime:
        items = [c for c in items if (c.get("runtime") or 0) <= max_runtime]
    if min_year:
        items = [c for c in items if (c.get("year") or 0) >= min_year]
    if max_year:
        items = [c for c in items if (c.get("year") or 0) <= max_year]

    if sort == "popular":
        items.sort(key=lambda c: c.get("popularity", 0), reverse=True)
    elif sort == "recent":
        items.sort(key=lambda c: c.get("year", 0), reverse=True)
    elif sort == "rating":
        items.sort(key=lambda c: c.get("external_rating", 0), reverse=True)
    else:  # recommended
        ctx = await build_user_context(user)
        scored = [(c, R.score_content(c, CONTENT_VECTORS[c["id"]], ctx["user_vector"], ctx)[0])
                  for c in items]
        scored.sort(key=lambda x: x[1], reverse=True)
        items = [c for c, _ in scored]
    return {"results": [public_content(c) for c in items[:120]], "count": len(items)}


@api.get("/contents/calibration")
async def calibration(user=Depends(get_current_user)):
    items = sorted(CONTENTS.values(), key=lambda c: c.get("popularity", 0), reverse=True)[:30]
    random.shuffle(items)
    return {"results": [public_content(c) for c in items[:20]]}


@api.get("/contents/{content_id}")
async def content_detail(content_id: str, user=Depends(get_current_user)):
    c = CONTENTS.get(content_id)
    if not c:
        raise HTTPException(404, "Content not found")
    ctx = await build_user_context(user)
    score, comp = R.score_content(c, CONTENT_VECTORS[content_id], ctx["user_vector"], ctx)
    match = max(1, min(99, round(score * 100)))
    reasons = R.generate_explanations(c, ctx)

    state = await db.user_content_states.find_one(
        {"user_id": user["id"], "content_id": content_id}, {"_id": 0})

    # community rating
    revs = await db.reviews.find(
        {"content_id": content_id, "deleted_at": None}, {"_id": 0}).to_list(500)
    rated = [r["rating"] for r in revs if r.get("rating")]
    community = round(sum(rated) / len(rated), 2) if rated else None

    # public reviews + author names
    public_reviews = [r for r in revs if r.get("visibility") == "public" or r["user_id"] == user["id"]]
    for r in public_reviews:
        author = await db.users.find_one({"id": r["user_id"]}, {"_id": 0})
        r["author"] = author.get("display_name") if author else "Unknown"
    public_reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    return {
        "content": c,
        "match_score": match,
        "components": comp,
        "reasons": reasons,
        "user_state": state,
        "community_rating": community,
        "community_votes": len(rated),
        "reviews": public_reviews[:50],
    }


# ===========================================================================
# Recommendations
# ===========================================================================
@api.get("/recommendations")
async def recommendations(context: str = "general", limit: int = 20,
                          user=Depends(get_current_user)):
    ctx = await build_user_context(user)
    return {"context": context, "results": rank_for_context(ctx, context, limit)}


@api.get("/recommendations/home")
async def home_feed(user=Depends(get_current_user)):
    ctx = await build_user_context(user)
    rails = [
        ("Recommended for you", "general"),
        ("Available on your platforms", "platforms"),
        ("New this week", "new"),
        ("Anime picks", "anime"),
    ]
    feed = []
    for title, key in rails:
        if key == "platforms" and not ctx.get("platforms"):
            continue
        items = rank_for_context(ctx, key, 12)
        if items:
            feed.append({"title": title, "context": key, "items": items})
    # hero = top general pick
    hero = feed[0]["items"][0] if feed and feed[0]["items"] else None
    return {"hero": hero, "rails": feed}


@api.get("/recommendations/{content_id}/reasons")
async def reco_reasons(content_id: str, user=Depends(get_current_user)):
    c = CONTENTS.get(content_id)
    if not c:
        raise HTTPException(404, "Content not found")
    ctx = await build_user_context(user)
    return {"reasons": R.generate_explanations(c, ctx)}


# ===========================================================================
# Events / states / watchlist
# ===========================================================================
EVENT_TO_STATE = {
    "like": "seen_liked", "dislike": "seen_disliked", "superlike": "seen_liked",
    "neutral": "seen_neutral", "abandoned": "abandoned", "watchlist": "watchlist",
}


async def recompute_user_vector(user_id):
    user = await db.users.find_one({"id": user_id})
    if not user:
        return
    ctx = await build_user_context(user)
    await db.user_vectors.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "vector_json": ctx["user_vector"],
                  "updated_at": now_iso()}}, upsert=True)
    # invalidate cache
    await db.recommendation_cache.delete_many({"user_id": user_id})


@api.post("/events")
async def record_event(body: EventBody, user=Depends(get_current_user)):
    if body.content_id not in CONTENTS:
        raise HTTPException(404, "Content not found")
    ev = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "content_id": body.content_id,
        "event_type": body.event_type, "event_value": body.event_value,
        "source": body.source, "confidence": 1.0, "context": "app",
        "created_at": now_iso(),
    }
    await db.user_events.insert_one(ev)

    # update state
    if body.event_type == "rating":
        await db.user_content_states.update_one(
            {"user_id": user["id"], "content_id": body.content_id},
            {"$set": {"rating": body.event_value, "updated_at": now_iso()},
             "$setOnInsert": {"user_id": user["id"], "content_id": body.content_id,
                              "state": "seen_neutral", "created_at": now_iso()}},
            upsert=True)
    elif body.event_type in EVENT_TO_STATE:
        await db.user_content_states.update_one(
            {"user_id": user["id"], "content_id": body.content_id},
            {"$set": {"state": EVENT_TO_STATE[body.event_type], "updated_at": now_iso()},
             "$setOnInsert": {"user_id": user["id"], "content_id": body.content_id,
                              "created_at": now_iso()}},
            upsert=True)

    await recompute_user_vector(user["id"])
    return {"ok": True, "event": ev["id"]}


@api.put("/contents/{content_id}/state")
async def set_state(content_id: str, body: StateBody, user=Depends(get_current_user)):
    if content_id not in CONTENTS:
        raise HTTPException(404, "Content not found")
    upd = {"updated_at": now_iso()}
    for f in ("state", "rating", "reaction", "is_excluded_from_reco"):
        v = getattr(body, f)
        if v is not None:
            upd[f] = v
    await db.user_content_states.update_one(
        {"user_id": user["id"], "content_id": content_id},
        {"$set": upd, "$setOnInsert": {"user_id": user["id"],
         "content_id": content_id, "created_at": now_iso()}}, upsert=True)
    await recompute_user_vector(user["id"])
    return await db.user_content_states.find_one(
        {"user_id": user["id"], "content_id": content_id}, {"_id": 0})


@api.post("/watchlist/{content_id}")
async def add_watchlist(content_id: str, user=Depends(get_current_user)):
    if content_id not in CONTENTS:
        raise HTTPException(404, "Content not found")
    await db.user_content_states.update_one(
        {"user_id": user["id"], "content_id": content_id},
        {"$set": {"state": "watchlist", "updated_at": now_iso()},
         "$setOnInsert": {"user_id": user["id"], "content_id": content_id,
                          "created_at": now_iso()}}, upsert=True)
    await recompute_user_vector(user["id"])
    return {"ok": True}


@api.delete("/watchlist/{content_id}")
async def remove_watchlist(content_id: str, user=Depends(get_current_user)):
    await db.user_content_states.update_one(
        {"user_id": user["id"], "content_id": content_id},
        {"$set": {"state": "not_seen", "updated_at": now_iso()}})
    return {"ok": True}


@api.get("/watchlist")
async def get_watchlist(user=Depends(get_current_user)):
    states = await db.user_content_states.find(
        {"user_id": user["id"], "state": "watchlist"}, {"_id": 0}).to_list(500)
    items = [public_content(CONTENTS[s["content_id"]])
             for s in states if s["content_id"] in CONTENTS]
    return {"results": items}


# ===========================================================================
# Reviews
# ===========================================================================
@api.post("/reviews")
async def create_review(body: ReviewBody, user=Depends(get_current_user)):
    if body.content_id not in CONTENTS:
        raise HTTPException(404, "Content not found")
    rev = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "content_id": body.content_id,
        "episode_id": None, "rating": body.rating, "reaction": body.reaction,
        "body": body.body, "is_spoiler": body.is_spoiler, "visibility": body.visibility,
        "created_at": now_iso(), "updated_at": now_iso(), "deleted_at": None,
    }
    await db.reviews.insert_one(rev)
    if body.rating is not None:
        await db.user_content_states.update_one(
            {"user_id": user["id"], "content_id": body.content_id},
            {"$set": {"rating": body.rating, "reaction": body.reaction,
                      "updated_at": now_iso()},
             "$setOnInsert": {"user_id": user["id"], "content_id": body.content_id,
                              "state": "seen_neutral", "created_at": now_iso()}},
            upsert=True)
        await recompute_user_vector(user["id"])
    rev.pop("_id", None)
    return rev


@api.get("/contents/{content_id}/reviews")
async def list_reviews(content_id: str, user=Depends(get_current_user)):
    revs = await db.reviews.find(
        {"content_id": content_id, "deleted_at": None}, {"_id": 0}).to_list(500)
    # respect visibility: public, or own
    out = []
    for r in revs:
        if r.get("visibility") == "public" or r["user_id"] == user["id"]:
            author = await db.users.find_one({"id": r["user_id"]}, {"_id": 0})
            r["author"] = author.get("display_name") if author else "Unknown"
            out.append(r)
    out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"results": out}


# ===========================================================================
# Rooms
# ===========================================================================
def gen_code(n=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


async def room_member_ids(room_id):
    mems = await db.room_members.find(
        {"room_id": room_id, "left_at": None}, {"_id": 0}).to_list(10)
    return [m["user_id"] for m in mems]


async def room_public(room):
    mems = await db.room_members.find(
        {"room_id": room["id"], "left_at": None}, {"_id": 0}).to_list(10)
    members = []
    for m in mems:
        u = await db.users.find_one({"id": m["user_id"]}, {"_id": 0})
        if u:
            members.append({"user_id": u["id"], "display_name": u.get("display_name"),
                            "avatar_url": u.get("avatar_url"), "role": m.get("role")})
    return {**{k: room.get(k) for k in (
        "id", "owner_id", "name", "join_code", "max_users", "threshold_percent",
        "quorum", "status", "round", "filters", "created_at")}, "members": members}


@api.post("/rooms")
async def create_room(body: RoomCreateBody, user=Depends(get_current_user)):
    rid = str(uuid.uuid4())
    room = {
        "id": rid, "owner_id": user["id"], "name": body.name, "visibility": "private",
        "join_code": gen_code(), "max_users": min(body.max_users, 5),
        "threshold_percent": body.threshold_percent, "quorum": body.quorum,
        "status": "lobby", "round": 1, "filters": body.filters.dict(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "created_at": now_iso(),
    }
    await db.rooms.insert_one(room)
    await db.room_members.insert_one({
        "room_id": rid, "user_id": user["id"], "role": "owner",
        "joined_at": now_iso(), "left_at": None})
    return await room_public(room)


@api.post("/rooms/join")
async def join_room(body: JoinBody, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"join_code": body.join_code.upper()})
    if not room:
        raise HTTPException(404, "Room not found")
    ids = await room_member_ids(room["id"])
    if user["id"] not in ids:
        if len(ids) >= room["max_users"]:
            raise HTTPException(400, "Room is full")
        await db.room_members.insert_one({
            "room_id": room["id"], "user_id": user["id"], "role": "member",
            "joined_at": now_iso(), "left_at": None})
    await broadcast(room["id"], {"type": "member_joined", "user": user.get("display_name")})
    return await room_public(room)


@api.get("/rooms")
async def my_rooms(user=Depends(get_current_user)):
    mems = await db.room_members.find(
        {"user_id": user["id"], "left_at": None}, {"_id": 0}).to_list(50)
    out = []
    for m in mems:
        room = await db.rooms.find_one({"id": m["room_id"]}, {"_id": 0})
        if room:
            out.append(await room_public(room))
    return {"results": out}


@api.get("/rooms/{room_id}")
async def get_room(room_id: str, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(404, "Room not found")
    return await room_public(room)


@api.put("/rooms/{room_id}/filters")
async def update_filters(room_id: str, body: RoomFiltersBody, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(404, "Room not found")
    if room["owner_id"] != user["id"]:
        raise HTTPException(403, "Only the owner can change filters")
    await db.rooms.update_one({"id": room_id}, {"$set": {"filters": body.dict()}})
    return await room_public(await db.rooms.find_one({"id": room_id}, {"_id": 0}))


async def generate_room_candidates(room):
    """Group-rank the catalog for the room and persist room_candidates."""
    member_ids = await room_member_ids(room["id"])
    filters = room.get("filters", {})
    # build per-member context
    contexts = {}
    member_states = {}
    for uid in member_ids:
        u = await db.users.find_one({"id": uid})
        if not u:
            continue
        states = await get_user_states(uid)
        member_states[uid] = {s["content_id"]: s for s in states}
        contexts[uid] = await build_user_context(u, states)

    # filter catalog
    def passes(c):
        if filters.get("formats") and c["type"] not in filters["formats"]:
            return False
        if filters.get("genres"):
            if not (set(g.lower() for g in c.get("genres", [])) &
                    set(g.lower() for g in filters["genres"])):
                return False
        if filters.get("platforms"):
            if not (set(c.get("providers", [])) & set(filters["platforms"])):
                return False
        if filters.get("min_rating") and (c.get("external_rating") or 0) < filters["min_rating"]:
            return False
        if filters.get("max_runtime") and (c.get("runtime") or 0) > filters["max_runtime"]:
            return False
        if filters.get("min_year") and (c.get("year") or 0) < filters["min_year"]:
            return False
        if filters.get("max_year") and (c.get("year") or 0) > filters["max_year"]:
            return False
        # seen filtering
        seen_by = sum(1 for uid in member_ids
                      if member_states.get(uid, {}).get(c["id"], {}).get("state")
                      in ("seen_liked", "seen_disliked", "seen_neutral", "abandoned"))
        if not filters.get("allow_seen_by_all", False) and seen_by == len(member_ids) and member_ids:
            return False
        if not filters.get("allow_seen_by_some", True) and seen_by > 0:
            return False
        return True

    candidates = [c for c in CONTENTS.values() if passes(c)]
    scored = []
    for c in candidates:
        member_scores, veto_count, shared_watch = [], 0, 0
        for uid in member_ids:
            ctx = contexts.get(uid)
            if not ctx:
                continue
            if c["id"] in ctx["excluded"]:
                veto_count += 1
            s, _ = R.score_content(c, CONTENT_VECTORS[c["id"]], ctx["user_vector"], ctx)
            member_scores.append(s)
            if member_states.get(uid, {}).get(c["id"], {}).get("state") == "watchlist":
                shared_watch += 1
        plats = set(filters.get("platforms", []))
        shared_platform = 1 if (plats & set(c.get("providers", []))) or not plats else 0
        gs, comp = R.group_score(member_scores, shared_watch / max(1, len(member_ids)),
                                 shared_platform, veto_count)
        reasons = R.group_explanation(len(member_ids), comp, shared_watch, shared_platform)
        scored.append((c, gs, comp, reasons))
    scored.sort(key=lambda x: x[1], reverse=True)

    await db.room_candidates.delete_many({"room_id": room["id"], "round": room.get("round", 1)})
    docs = []
    for rank, (c, gs, comp, reasons) in enumerate(scored[:30]):
        docs.append({
            "room_id": room["id"], "round": room.get("round", 1), "content_id": c["id"],
            "rank": rank, "group_score": round(gs, 4), "components": comp,
            "reasons": reasons, "status": "active", "created_at": now_iso()})
    if docs:
        await db.room_candidates.insert_many(docs)
    return len(docs)


@api.post("/rooms/{room_id}/start")
async def start_room(room_id: str, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(404, "Room not found")
    if room["owner_id"] != user["id"]:
        raise HTTPException(403, "Only the owner can start")
    n = await generate_room_candidates(room)
    await db.rooms.update_one({"id": room_id}, {"$set": {"status": "voting"}})
    await broadcast(room_id, {"type": "room_started", "candidates": n})
    return {"ok": True, "candidates": n}


@api.get("/rooms/{room_id}/candidates")
async def room_candidates(room_id: str, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(404, "Room not found")
    cands = await db.room_candidates.find(
        {"room_id": room_id, "round": room.get("round", 1)}, {"_id": 0}
    ).sort("rank", 1).to_list(50)
    results = []
    for c in cands:
        content = CONTENTS.get(c["content_id"])
        if content:
            results.append({"content": public_content(content),
                            "group_score": c["group_score"], "reasons": c["reasons"]})
    return {"results": results, "status": room.get("status")}


@api.post("/rooms/{room_id}/vote")
async def vote(room_id: str, body: VoteBody, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(404, "Room not found")
    rnd = room.get("round", 1)
    await db.room_votes.update_one(
        {"room_id": room_id, "round": rnd, "content_id": body.content_id,
         "user_id": user["id"]},
        {"$set": {"vote": body.vote, "created_at": now_iso()}}, upsert=True)
    summary = await compute_winner(room)
    await broadcast(room_id, {"type": "vote_update", "summary": summary,
                              "voter": user.get("display_name")})
    return summary


async def compute_winner(room):
    rnd = room.get("round", 1)
    member_ids = await room_member_ids(room["id"])
    quorum = room.get("quorum", 2)
    threshold = room.get("threshold_percent", 60) / 100.0
    votes = await db.room_votes.find(
        {"room_id": room["id"], "round": rnd}, {"_id": 0}).to_list(2000)

    by_content = {}
    for v in votes:
        by_content.setdefault(v["content_id"], []).append(v["vote"])

    tallies = []
    for cid, vs in by_content.items():
        total = len(vs)
        likes = vs.count("like")
        supers = vs.count("superlike")
        dislikes = vs.count("dislike")
        vetoes = vs.count("veto")
        agreement = (likes + supers) / total if total else 0
        tie = 2 * supers + likes - dislikes
        wins = (agreement >= threshold and total >= quorum and vetoes == 0)
        tallies.append({
            "content_id": cid, "total_votes": total, "likes": likes,
            "superlikes": supers, "dislikes": dislikes, "vetoes": vetoes,
            "agreement_rate": round(agreement, 3), "tie_score": tie, "wins": wins})

    winners = [t for t in tallies if t["wins"]]
    winners.sort(key=lambda t: (t["tie_score"], t["agreement_rate"]), reverse=True)
    candidates = sorted(tallies, key=lambda t: (t["agreement_rate"], t["tie_score"]),
                        reverse=True)

    def enrich(t):
        c = CONTENTS.get(t["content_id"])
        return {**t, "content": public_content(c) if c else None}

    winner = enrich(winners[0]) if winners else None
    top3 = [enrich(t) for t in candidates[:3]]

    if winner:
        await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": "decided"}})
    return {"winner": winner, "top_candidates": top3, "round": rnd,
            "threshold_percent": room.get("threshold_percent"),
            "quorum": quorum, "members": len(member_ids)}


@api.get("/rooms/{room_id}/result")
async def room_result(room_id: str, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(404, "Room not found")
    return await compute_winner(room)


@api.post("/rooms/{room_id}/relaunch")
async def relaunch(room_id: str, body: RelaunchBody, user=Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(404, "Room not found")
    if room["owner_id"] != user["id"]:
        raise HTTPException(403, "Only the owner can relaunch")
    upd = {"round": room.get("round", 1) + 1, "status": "voting"}
    if body.threshold_percent is not None:
        upd["threshold_percent"] = body.threshold_percent
    if body.filters is not None:
        upd["filters"] = body.filters.dict()
    await db.rooms.update_one({"id": room_id}, {"$set": upd})
    room = await db.rooms.find_one({"id": room_id})
    n = await generate_room_candidates(room)
    await broadcast(room_id, {"type": "relaunched", "round": room["round"]})
    return {"ok": True, "round": room["round"], "candidates": n}


# ===========================================================================
# WebSocket
# ===========================================================================
class WSManager:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, room_id, ws):
        await ws.accept()
        self.rooms.setdefault(room_id, []).append(ws)

    def disconnect(self, room_id, ws):
        if room_id in self.rooms and ws in self.rooms[room_id]:
            self.rooms[room_id].remove(ws)

    async def broadcast(self, room_id, message):
        for ws in list(self.rooms.get(room_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(room_id, ws)


manager = WSManager()


async def broadcast(room_id, message):
    await manager.broadcast(room_id, message)


@app.websocket("/api/ws/rooms/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str):
    await manager.connect(room_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive / pings
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)


# ===========================================================================
# Dev / daily job
# ===========================================================================
@api.post("/dev/run-daily-job")
async def run_daily_job():
    """
    Daily recomputation job (scaffold). In production this runs on a scheduler.
    Steps: refresh metadata/providers/scores (external), recompute content
    features, recompute user vectors, regenerate per-user recommendation cache.
    # TODO: wire to a scheduler (APScheduler / cron) and external service layer.
    """
    await load_feature_store()
    users = await db.users.find({"deleted_at": None}, {"_id": 0}).to_list(1000)
    cached = 0
    contexts = ["top_100_general", "top_50_movies", "top_50_series", "top_50_anime",
                "top_50_available_on_owned_platforms", "top_50_new_releases"]
    ctx_map = {"top_100_general": ("general", 100), "top_50_movies": ("movies", 50),
               "top_50_series": ("series", 50), "top_50_anime": ("anime", 50),
               "top_50_available_on_owned_platforms": ("platforms", 50),
               "top_50_new_releases": ("new", 50)}
    for u in users:
        uctx = await build_user_context(u)
        await db.recommendation_cache.delete_many({"user_id": u["id"]})
        for ckey in contexts:
            context, lim = ctx_map[ckey]
            ranked = rank_for_context(uctx, context, lim)
            docs = [{"user_id": u["id"], "context_key": ckey,
                     "content_id": r["content"]["id"], "score": r["match_score"],
                     "rank": i, "reasons": r["reasons"], "model_version": "v1",
                     "created_at": now_iso()} for i, r in enumerate(ranked)]
            if docs:
                await db.recommendation_cache.insert_many(docs)
                cached += len(docs)
    return {"ok": True, "users": len(users), "cached": cached}


# ===========================================================================
# TMDB integration (backend-only; gated by licensing.can_use_tmdb)
# ===========================================================================
async def upsert_content(normalized: dict):
    """Insert or update a TMDB-normalized content. Returns (doc, created)."""
    tmdb_id = (normalized.get("external_ids") or {}).get("tmdb")
    existing = None
    if tmdb_id:
        existing = await db.contents.find_one({"external_ids.tmdb": tmdb_id}, {"_id": 0})
    if not existing:
        existing = await db.contents.find_one(
            {"title": normalized.get("title"), "year": normalized.get("year"),
             "type": normalized.get("type")}, {"_id": 0})
    now = now_iso()
    if existing:
        upd = {k: v for k, v in normalized.items() if v not in (None, [], "")}
        upd["updated_at"] = now
        await db.contents.update_one({"id": existing["id"]}, {"$set": upd})
        merged = {**existing, **upd}
        CONTENTS[merged["id"]] = merged
        CONTENT_VECTORS[merged["id"]] = R.build_content_vector(merged)
        return merged, False
    doc = {
        "id": str(uuid.uuid4()), "source": "tmdb",
        "source_id": str(tmdb_id) if tmdb_id else (normalized.get("title") or "tmdb"),
        "status": "released", "keywords": normalized.get("keywords", []),
        "seasons": normalized.get("seasons", 0), "episodes": normalized.get("episodes", 0),
        "created_at": now, "updated_at": now, **normalized,
    }
    await db.contents.insert_one({**doc})
    CONTENTS[doc["id"]] = doc
    CONTENT_VECTORS[doc["id"]] = R.build_content_vector(doc)
    return doc, True


@api.get("/search")
async def search(q: str = "", type: str = "all", page: int = 1, language: str = "",
                 user=Depends(get_current_user)):
    q = (q or "").strip()
    if not q:
        return {"results": [], "source": "none"}
    ql = q.lower()
    local = [c for c in CONTENTS.values()
             if ql in c["title"].lower() or ql in (c.get("original_title", "") or "").lower()]
    if type in ("movie", "series", "anime"):
        local = [c for c in local if c["type"] == type]
    results = [public_content(c) for c in local[:30]]
    source = "seed"

    # anime is not reliably mapped on TMDB -> seeded catalog only
    if tmdb.tmdb_enabled() and type != "anime":
        lang = language or None
        normalized = []
        if type in ("movie", "all"):
            for m in (await tmdb.search_movies(q, page, lang))[:10]:
                normalized.append(tmdb.normalize_tmdb_movie(m))
        if type in ("series", "all"):
            for t in (await tmdb.search_tv(q, page, lang))[:10]:
                normalized.append(tmdb.normalize_tmdb_tv(t))
        seen = {(r["title"], r.get("year")) for r in results}
        for n in normalized:
            if not n.get("title") or not n.get("poster_url"):
                continue
            if (n["title"], n.get("year")) in seen:
                continue
            seen.add((n["title"], n.get("year")))
            stored, _ = await upsert_content(n)
            results.append(public_content(stored))
        source = "tmdb+seed"
    return {"results": results[:40], "source": source, "provider_status": get_provider_status()}


@api.get("/contents/{content_id}/enrich")
async def enrich_content(content_id: str, country: str = "", user=Depends(get_current_user)):
    c = CONTENTS.get(content_id)
    if not c:
        raise HTTPException(404, "Content not found")
    if not tmdb.tmdb_enabled():
        return {"content": c, "enriched": False, "provider_status": get_provider_status()}
    fields = await tmdb.enrich_content_from_tmdb(c, country or None)
    if not fields:
        return {"content": c, "enriched": False, "provider_status": get_provider_status()}
    upd = {k: v for k, v in fields.items() if v not in (None, [], "")}
    upd["external_ids"] = {**(c.get("external_ids") or {}), **(fields.get("external_ids") or {})}
    upd["updated_at"] = now_iso()
    await db.contents.update_one({"id": content_id}, {"$set": upd})
    merged = {**c, **upd}
    CONTENTS[content_id] = merged
    CONTENT_VECTORS[content_id] = R.build_content_vector(merged)
    return {"content": merged, "enriched": True}


@api.post("/contents/refresh-trending")
async def refresh_trending(user=Depends(get_current_user)):
    if not tmdb.tmdb_enabled():
        return {"inserted_count": 0, "updated_count": 0, "skipped_count": 0,
                "provider_status": get_provider_status()}
    inserted = updated = skipped = 0
    for kind in ("movie", "tv"):
        for it in (await tmdb.get_trending(kind, "week"))[:15]:
            n = tmdb.normalize_tmdb_movie(it) if kind == "movie" else tmdb.normalize_tmdb_tv(it)
            if not n.get("title") or not n.get("poster_url"):
                skipped += 1
                continue
            _, created = await upsert_content(n)
            inserted += 1 if created else 0
            updated += 0 if created else 1
    return {"inserted_count": inserted, "updated_count": updated, "skipped_count": skipped}


@api.get("/providers/{content_id}")
async def content_providers(content_id: str, country: str = "", user=Depends(get_current_user)):
    c = CONTENTS.get(content_id)
    if not c:
        raise HTTPException(404, "Content not found")
    country = country or os.environ.get("DEFAULT_COUNTRY", "FR")
    cached = c.get("providers") or []
    if tmdb.tmdb_enabled():
        tmdb_id = (c.get("external_ids") or {}).get("tmdb")
        if tmdb_id:
            ctype = "movie" if c["type"] == "movie" else "tv"
            fresh = await tmdb.get_watch_providers(ctype, tmdb_id, country)
            if fresh:
                await db.contents.update_one(
                    {"id": content_id}, {"$set": {"providers": fresh, "updated_at": now_iso()}})
                CONTENTS[content_id] = {**c, "providers": fresh}
                return {"providers": fresh, "country": country, "source": "tmdb"}
    return {"providers": cached, "country": country, "source": "seed"}


@api.get("/provider-status")
async def provider_status():
    return get_provider_status()


@api.get("/")
async def root():
    return {"message": "SwipeNight API", "contents": len(CONTENTS)}


# ===========================================================================
# Seeding
# ===========================================================================
FAKE_USERS = [
    ("alex_noir", "Alex", ["Netflix", "Max"], ["movies", "series"],
     ["Thriller", "Sci-Fi", "Crime"], ["dark", "intense"]),
    ("mika_films", "Mika", ["Crunchyroll", "Netflix"], ["anime", "series"],
     ["Action", "Fantasy", "Adventure"], ["intense", "group"]),
    ("sam_chill", "Sam", ["Prime Video", "Disney+"], ["movies"],
     ["Comedy", "Romance", "Drama"], ["light", "funny"]),
    ("rae_binge", "Rae", ["Max", "Apple TV+"], ["series", "movies"],
     ["Drama", "Crime", "Thriller"], ["emotional", "long"]),
    ("kai_otaku", "Kai", ["Crunchyroll"], ["anime"],
     ["Action", "Fantasy", "Drama"], ["intense", "solo"]),
]


async def seed_fake_users_and_content():
    catalog = list(CONTENTS.values())
    by_type = {"movie": [], "series": [], "anime": []}
    for c in catalog:
        by_type[c["type"]].append(c)

    for username, name, platforms, formats, genres, moods in FAKE_USERS:
        if await db.users.find_one({"username": username}):
            continue
        uid = str(uuid.uuid4())
        await db.users.insert_one({
            "id": uid, "email": f"{username}@swipenight.app", "username": username,
            "display_name": name, "avatar_url": None, "is_anonymous": False,
            "hashed_password": hash_password("password123"),
            "preferences": {"onboarded": True, "platforms": platforms,
                            "formats": formats, "genres": genres, "moods": moods,
                            "country": "US"},
            "created_at": now_iso(), "deleted_at": None})
        await db.user_privacy_settings.insert_one({
            "user_id": uid, "history_visibility": "private",
            "ratings_visibility": "public", "watchlist_visibility": "friends",
            "profile_visibility": "public"})
        # generate states/ratings/reviews matching their genre taste
        pool = []
        for f in formats:
            pool += by_type.get("movie" if f == "movies" else f, [])
        random.shuffle(pool)
        for c in pool[:18]:
            match = set(g.lower() for g in c["genres"]) & set(g.lower() for g in genres)
            if match:
                state, rating = random.choice(
                    [("seen_liked", 4.5), ("seen_liked", 5.0), ("watchlist", None)])
            else:
                state, rating = random.choice(
                    [("seen_disliked", 2.0), ("seen_neutral", 3.0), ("abandoned", 1.5)])
            await db.user_content_states.insert_one({
                "user_id": uid, "content_id": c["id"], "state": state,
                "rating": rating, "reaction": None, "is_excluded_from_reco": False,
                "created_at": now_iso(),
                "updated_at": (datetime.now(timezone.utc)
                               - timedelta(days=random.randint(1, 120))).isoformat()})
            if rating and rating >= 4.5 and random.random() < 0.4:
                await db.reviews.insert_one({
                    "id": str(uuid.uuid4()), "user_id": uid, "content_id": c["id"],
                    "episode_id": None, "rating": rating,
                    "reaction": random.choice(["loved", "masterpiece", "intense", "surprising"]),
                    "body": random.choice([
                        "Absolutely loved this — couldn't stop watching.",
                        "A masterpiece. Highly recommend.",
                        "Intense from start to finish.",
                        "One of my favourites this year."]),
                    "is_spoiler": False, "visibility": "public",
                    "created_at": now_iso(), "updated_at": now_iso(), "deleted_at": None})


async def seed_demo_room():
    if await db.rooms.find_one({"name": "Friday Movie Night"}):
        return
    owner = await db.users.find_one({"username": "alex_noir"})
    if not owner:
        return
    rid = str(uuid.uuid4())
    await db.rooms.insert_one({
        "id": rid, "owner_id": owner["id"], "name": "Friday Movie Night",
        "visibility": "private", "join_code": "MOVIE1", "max_users": 5,
        "threshold_percent": 60, "quorum": 2, "status": "lobby", "round": 1,
        "filters": RoomFiltersBody().dict(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "created_at": now_iso()})
    for username, role in [("alex_noir", "owner"), ("sam_chill", "member"),
                           ("rae_binge", "member")]:
        u = await db.users.find_one({"username": username})
        if u:
            await db.room_members.insert_one({
                "room_id": rid, "user_id": u["id"], "role": role,
                "joined_at": now_iso(), "left_at": None})


@app.on_event("startup")
async def startup():
    if await db.contents.count_documents({}) == 0:
        catalog = build_catalog()
        await db.contents.insert_many([{**c} for c in catalog])
        logger.info("Seeded %d contents", len(catalog))
    await load_feature_store()
    reason = tmdb_disabled_reason()
    if reason:
        logger.warning("TMDB disabled (%s) — using seeded catalog fallback.", reason)
    else:
        logger.info("TMDB enabled (free non-commercial beta mode).")
    await seed_fake_users_and_content()
    await seed_demo_room()
    logger.info("SwipeNight startup complete")


@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api)
app.add_middleware(
    CORSMiddleware, allow_credentials=True, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])
