"""
TMDB service — backend-only. The API key never leaves the backend.

All calls are gated by licensing.can_use_tmdb(). When TMDB is disabled (no key,
external APIs off, or commercial mode without a confirmed license) every function
degrades gracefully (returns [] / None / the unchanged input) so the app keeps
working on the seeded catalog.

Results are normalized into the existing SwipeNight content schema so the
recommendation engine and UI consume them without changes.
"""
import logging
import os

import httpx

from licensing import can_use_tmdb

logger = logging.getLogger("swipenight.tmdb")

BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"
TIMEOUT = 8.0

# Minimal TMDB genre id -> name maps (used for light search normalization).
MOVIE_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance",
    878: "Sci-Fi", 53: "Thriller", 10752: "War", 37: "Western",
}
TV_GENRES = {
    10759: "Action", 16: "Animation", 35: "Comedy", 80: "Crime", 99: "Documentary",
    18: "Drama", 10751: "Family", 9648: "Mystery", 10765: "Sci-Fi", 37: "Western",
    10768: "War", 10764: "Reality",
}


def tmdb_enabled() -> bool:
    return can_use_tmdb()


def _lang() -> str:
    return os.environ.get("TMDB_DEFAULT_LANGUAGE", "fr-FR")


def _fallback_lang() -> str:
    return os.environ.get("TMDB_FALLBACK_LANGUAGE", "en-US")


def _img(path, size="w500"):
    return f"{IMG}/{size}{path}" if path else None


async def tmdb_request(endpoint: str, params: dict | None = None):
    """Low-level GET against TMDB. Returns parsed JSON or None on any failure."""
    if not tmdb_enabled():
        return None
    p = dict(params or {})
    p["api_key"] = os.environ.get("TMDB_API_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{BASE}{endpoint}", params=p)
            if r.status_code != 200:
                logger.warning("TMDB %s -> %s", endpoint, r.status_code)
                return None
            return r.json()
    except Exception as e:  # network / timeout / parse — never crash the app
        logger.warning("TMDB request failed (%s): %s", endpoint, e)
        return None


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
async def search_movies(query, page=1, language=None):
    data = await tmdb_request("/search/movie",
                              {"query": query, "page": page, "language": language or _lang()})
    return (data or {}).get("results", []) if data else []


async def search_tv(query, page=1, language=None):
    data = await tmdb_request("/search/tv",
                              {"query": query, "page": page, "language": language or _lang()})
    return (data or {}).get("results", []) if data else []


# --------------------------------------------------------------------------
# Details / credits / videos / providers
# --------------------------------------------------------------------------
async def _details_with_fallback(endpoint, language):
    data = await tmdb_request(endpoint, {"language": language or _lang()})
    if data and not (data.get("overview") or "").strip():
        # French overview missing -> grab English text fields
        en = await tmdb_request(endpoint, {"language": _fallback_lang()})
        if en:
            data["overview"] = en.get("overview") or data.get("overview")
    return data


async def get_movie_details(tmdb_id, language=None):
    return await _details_with_fallback(f"/movie/{tmdb_id}", language)


async def get_tv_details(tmdb_id, language=None):
    return await _details_with_fallback(f"/tv/{tmdb_id}", language)


async def get_movie_credits(tmdb_id):
    return await tmdb_request(f"/movie/{tmdb_id}/credits") or {}


async def get_tv_credits(tmdb_id):
    return await tmdb_request(f"/tv/{tmdb_id}/credits") or {}


async def get_movie_videos(tmdb_id, language=None):
    return await tmdb_request(f"/movie/{tmdb_id}/videos", {"language": language or _lang()}) or {}


async def get_tv_videos(tmdb_id, language=None):
    return await tmdb_request(f"/tv/{tmdb_id}/videos", {"language": language or _lang()}) or {}


async def get_watch_providers(content_type, tmdb_id, country=None):
    country = country or os.environ.get("DEFAULT_COUNTRY", "FR")
    path = "movie" if content_type == "movie" else "tv"
    data = await tmdb_request(f"/{path}/{tmdb_id}/watch/providers")
    if not data:
        return []
    region = (data.get("results") or {}).get(country, {})
    names = []
    for bucket in ("flatrate", "free", "ads", "rent", "buy"):
        for prov in region.get(bucket, []) or []:
            n = prov.get("provider_name")
            if n and n not in names:
                names.append(n)
    return names


async def get_trending(content_type="all", time_window="week"):
    data = await tmdb_request(f"/trending/{content_type}/{time_window}")
    return (data or {}).get("results", []) if data else []


# --------------------------------------------------------------------------
# Normalization into the SwipeNight content schema
# --------------------------------------------------------------------------
def _trailer(videos):
    for v in (videos or {}).get("results", []):
        if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser"):
            return f"https://www.youtube.com/watch?v={v.get('key')}"
    return None


def _quality(vote_average, vote_count, C=6.8, m=50):
    if (vote_count + m) == 0:
        return C
    return round((vote_count / (vote_count + m)) * vote_average + (m / (vote_count + m)) * C, 3)


def normalize_tmdb_movie(movie, credits=None, videos=None, providers=None, country=None):
    year = None
    if movie.get("release_date"):
        year = int(movie["release_date"][:4]) if movie["release_date"][:4].isdigit() else None
    genres = [g["name"] for g in movie.get("genres", [])] or \
             [MOVIE_GENRES.get(i) for i in movie.get("genre_ids", []) if MOVIE_GENRES.get(i)]
    cast = [c["name"] for c in (credits or {}).get("cast", [])[:6]]
    director = next((c["name"] for c in (credits or {}).get("crew", [])
                     if c.get("job") == "Director"), None)
    return {
        "type": "movie",
        "title": movie.get("title") or movie.get("original_title"),
        "original_title": movie.get("original_title"),
        "year": year,
        "overview": movie.get("overview") or "",
        "poster_url": _img(movie.get("poster_path")),
        "backdrop_url": _img(movie.get("backdrop_path"), "w780"),
        "runtime": movie.get("runtime") or 0,
        "genres": [g for g in genres if g],
        "keywords": [],
        "cast": cast,
        "crew": [director] if director else [],
        "creator": director,
        "studios": [s["name"] for s in movie.get("production_companies", [])[:2]],
        "countries": [c["iso_3166_1"] for c in movie.get("production_countries", [])] or ["US"],
        "languages": [movie["original_language"]] if movie.get("original_language") else ["en"],
        "trailer_url": _trailer(videos),
        "popularity": round(min(100, movie.get("popularity", 0)), 2),
        "popularity_score": round(min(100, movie.get("popularity", 0)), 2),
        "external_rating": movie.get("vote_average") or 0,
        "vote_average": movie.get("vote_average") or 0,
        "vote_count": movie.get("vote_count") or 0,
        "quality_score": _quality(movie.get("vote_average") or 0, movie.get("vote_count") or 0),
        "providers": providers if providers is not None else [],
        "external_ids": {"tmdb": movie.get("id"), "imdb": movie.get("imdb_id")},
        "metadata_source": "tmdb",
        "image_source": "tmdb",
    }


def normalize_tmdb_tv(tv, credits=None, videos=None, providers=None, country=None):
    year = None
    if tv.get("first_air_date"):
        year = int(tv["first_air_date"][:4]) if tv["first_air_date"][:4].isdigit() else None
    genres = [g["name"] for g in tv.get("genres", [])] or \
             [TV_GENRES.get(i) for i in tv.get("genre_ids", []) if TV_GENRES.get(i)]
    cast = [c["name"] for c in (credits or {}).get("cast", [])[:6]]
    creators = [c["name"] for c in tv.get("created_by", [])]
    creator = creators[0] if creators else None
    runtime = (tv.get("episode_run_time") or [0])
    return {
        "type": "series",
        "title": tv.get("name") or tv.get("original_name"),
        "original_title": tv.get("original_name"),
        "year": year,
        "overview": tv.get("overview") or "",
        "poster_url": _img(tv.get("poster_path")),
        "backdrop_url": _img(tv.get("backdrop_path"), "w780"),
        "runtime": runtime[0] if runtime else 0,
        "genres": [g for g in genres if g],
        "keywords": [],
        "cast": cast,
        "crew": creators,
        "creator": creator,
        "studios": [s["name"] for s in tv.get("production_companies", [])[:2]],
        "countries": tv.get("origin_country") or ["US"],
        "languages": [tv["original_language"]] if tv.get("original_language") else ["en"],
        "trailer_url": _trailer(videos),
        "popularity": round(min(100, tv.get("popularity", 0)), 2),
        "popularity_score": round(min(100, tv.get("popularity", 0)), 2),
        "external_rating": tv.get("vote_average") or 0,
        "vote_average": tv.get("vote_average") or 0,
        "vote_count": tv.get("vote_count") or 0,
        "quality_score": _quality(tv.get("vote_average") or 0, tv.get("vote_count") or 0),
        "providers": providers if providers is not None else [],
        "seasons": tv.get("number_of_seasons") or 0,
        "episodes": tv.get("number_of_episodes") or 0,
        "external_ids": {"tmdb": tv.get("id")},
        "metadata_source": "tmdb",
        "image_source": "tmdb",
    }


async def enrich_content_from_tmdb(content, country=None):
    """
    Given a local content doc, fetch full TMDB metadata and return a dict of
    fields to merge. Returns {} when TMDB is disabled or nothing found.
    Only non-empty values overwrite the seeded content (handled by caller).
    """
    if not tmdb_enabled():
        return {}
    country = country or os.environ.get("DEFAULT_COUNTRY", "FR")
    ctype = "movie" if content.get("type") == "movie" else "tv"
    tmdb_id = (content.get("external_ids") or {}).get("tmdb")

    # No tmdb id yet -> try to resolve via search by title (+year)
    if not tmdb_id:
        results = (await search_movies(content["title"]) if ctype == "movie"
                   else await search_tv(content["title"]))
        if content.get("year"):
            yr = str(content["year"])
            key = "release_date" if ctype == "movie" else "first_air_date"
            results = sorted(results, key=lambda r: 0 if str(r.get(key, "")).startswith(yr) else 1)
        if results:
            tmdb_id = results[0].get("id")
    if not tmdb_id:
        return {}

    if ctype == "movie":
        details = await get_movie_details(tmdb_id)
        if not details:
            return {}
        credits = await get_movie_credits(tmdb_id)
        videos = await get_movie_videos(tmdb_id)
        providers = await get_watch_providers("movie", tmdb_id, country)
        return normalize_tmdb_movie(details, credits, videos, providers, country)
    else:
        details = await get_tv_details(tmdb_id)
        if not details:
            return {}
        credits = await get_tv_credits(tmdb_id)
        videos = await get_tv_videos(tmdb_id)
        providers = await get_watch_providers("tv", tmdb_id, country)
        return normalize_tmdb_tv(details, credits, videos, providers, country)
