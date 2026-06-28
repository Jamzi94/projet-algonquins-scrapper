"""
Tests for TMDB licensing guardrails, graceful service degradation, and that the
recommender uses enriched metadata. No network/DB required.

Run: cd /app/backend && python -m pytest tests/test_tmdb_licensing.py -v
"""
import asyncio
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reload_licensing(env):
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import licensing
    importlib.reload(licensing)
    return licensing


# 1. TMDB disabled if no API key
def test_disabled_when_no_key():
    lic = _reload_licensing({"TMDB_API_KEY": "", "EXTERNAL_APIS_ENABLED": "true",
                             "COMMERCIAL_MODE": "false",
                             "TMDB_COMMERCIAL_LICENSE_CONFIRMED": "false"})
    assert lic.can_use_tmdb() is False


# 2. TMDB disabled if commercial mode and license not confirmed
def test_disabled_commercial_unconfirmed():
    lic = _reload_licensing({"TMDB_API_KEY": "key", "EXTERNAL_APIS_ENABLED": "true",
                             "COMMERCIAL_MODE": "true",
                             "TMDB_COMMERCIAL_LICENSE_CONFIRMED": "false"})
    assert lic.can_use_tmdb() is False
    assert "commercial" in (lic.tmdb_disabled_reason() or "").lower()


# 3. TMDB allowed in free non-commercial mode with a key
def test_allowed_noncommercial_with_key():
    lic = _reload_licensing({"TMDB_API_KEY": "key", "EXTERNAL_APIS_ENABLED": "true",
                             "COMMERCIAL_MODE": "false",
                             "TMDB_COMMERCIAL_LICENSE_CONFIRMED": "false"})
    assert lic.can_use_tmdb() is True
    assert lic.tmdb_disabled_reason() is None


# 4. TMDB allowed in commercial mode when license confirmed
def test_allowed_commercial_confirmed():
    lic = _reload_licensing({"TMDB_API_KEY": "key", "EXTERNAL_APIS_ENABLED": "true",
                             "COMMERCIAL_MODE": "true",
                             "TMDB_COMMERCIAL_LICENSE_CONFIRMED": "true"})
    assert lic.can_use_tmdb() is True


def test_external_apis_master_switch():
    lic = _reload_licensing({"TMDB_API_KEY": "key", "EXTERNAL_APIS_ENABLED": "false",
                             "COMMERCIAL_MODE": "false"})
    assert lic.can_use_tmdb() is False


# 9. Provider status utility works
def test_provider_status_shape():
    lic = _reload_licensing({"TMDB_API_KEY": "", "EXTERNAL_APIS_ENABLED": "true"})
    s = lic.get_provider_status()
    assert s["tmdb_enabled"] is False
    assert s["seed_catalog_fallback"] is True
    assert s["reason"]


# 5 & 6. TMDB service degrades safely when disabled (search empty, enrich no-op)
def test_tmdb_service_degrades_when_disabled():
    _reload_licensing({"TMDB_API_KEY": "", "EXTERNAL_APIS_ENABLED": "true"})
    import services.external.tmdb as tmdb
    importlib.reload(tmdb)
    assert tmdb.tmdb_enabled() is False
    assert asyncio.run(tmdb.search_movies("dune")) == []
    assert asyncio.run(tmdb.search_tv("dark")) == []
    assert asyncio.run(tmdb.enrich_content_from_tmdb({"type": "movie", "title": "X"})) == {}
    assert asyncio.run(tmdb.get_watch_providers("movie", 1)) == []


# 7. Recommender still works with seeded-only content
def test_recommender_seeded_only():
    import recommender as R
    c = {"id": "x", "genres": ["Drama"], "external_rating": 7, "vote_count": 100,
         "popularity": 40, "year": 2010, "runtime": 110, "providers": ["Netflix"]}
    ctx = {"platforms": ["Netflix"], "moods": [], "rejected_genres": set(),
           "state_map": {}, "excluded": set(), "has_taste": False, "preferred_genres": []}
    s, comp = R.score_content(c, R.build_content_vector(c), {}, ctx)
    assert 0 <= s <= 2 and "taste" in comp


# 8. Recommender improves/uses enriched metadata when available
def test_recommender_uses_enriched_metadata():
    import recommender as R
    bare = {"id": "a", "genres": [], "external_rating": 0, "vote_count": 0,
            "popularity": 0, "year": 2000, "runtime": 120, "providers": []}
    enriched = {"id": "b", "genres": ["Sci-Fi", "Thriller"], "cast": ["X"],
                "crew": ["Y"], "overview": "space time future dystopia",
                "external_rating": 8.5, "vote_count": 5000, "popularity": 90,
                "year": 2024, "runtime": 120, "providers": ["Netflix"],
                "metadata_source": "tmdb"}
    ctx = {"platforms": ["Netflix"], "moods": [], "rejected_genres": set(),
           "state_map": {}, "excluded": set(), "has_taste": False,
           "preferred_genres": ["Sci-Fi"]}
    sb, _ = R.score_content(bare, R.build_content_vector(bare), {}, ctx)
    se, _ = R.score_content(enriched, R.build_content_vector(enriched), {}, ctx)
    assert se > sb  # richer metadata + availability + quality ranks higher


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
