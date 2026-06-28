"""
Validation tests for SwipeNight core logic (pure functions, no DB needed).
Run: cd /app/backend && python -m pytest tests/test_recommender.py -v
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recommender as R


def test_bayesian_score_protects_obscure_content():
    # Obscure content (few votes) is pulled toward the global mean C.
    obscure = R.bayesian_score(10.0, 2)        # rating 10 but only 2 votes
    popular = R.bayesian_score(8.5, 5000)
    assert obscure < popular
    assert abs(R.bayesian_score(R.BAYES_C, 0) - R.BAYES_C) < 1e-9


def test_cosine_similarity():
    a = {"genre:scifi": 1.0, "cast:x": 0.5}
    assert abs(R.cosine(a, a) - 1.0) < 1e-9
    assert R.cosine(a, {"genre:romance": 1.0}) == 0.0


def test_user_vector_positive_minus_negative():
    cv = {
        "c1": {"genre:scifi": 1.0},
        "c2": {"genre:romance": 1.0},
    }
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    interactions = [
        {"content_id": "c1", "signal": 3, "ts": now},   # like scifi
        {"content_id": "c2", "signal": -3, "ts": now},  # dislike romance
    ]
    uv = R.build_user_vector(interactions, cv)
    assert uv["genre:scifi"] > 0
    assert uv["genre:romance"] < 0


def test_already_seen_penalty_applied():
    content = {"id": "x", "genres": ["Sci-Fi"], "external_rating": 8, "vote_count": 1000,
               "popularity": 50, "year": 2020, "runtime": 120, "providers": ["Netflix"]}
    cv = R.build_content_vector(content)
    base_ctx = {"platforms": ["Netflix"], "moods": [], "rejected_genres": set(),
                "state_map": {}, "excluded": set(), "has_taste": False, "preferred_genres": []}
    seen_ctx = {**base_ctx, "state_map": {"x": "seen_liked"}}
    base, _ = R.score_content(content, cv, {}, base_ctx)
    seen, _ = R.score_content(content, cv, {}, seen_ctx)
    assert seen < base  # seen content is penalised


def test_platform_availability_score():
    content = {"id": "x", "genres": ["Drama"], "external_rating": 7, "vote_count": 500,
               "popularity": 40, "year": 2021, "runtime": 100, "providers": ["Max"]}
    cv = R.build_content_vector(content)
    match = {"platforms": ["Max"], "moods": [], "rejected_genres": set(), "state_map": {},
             "excluded": set(), "has_taste": False, "preferred_genres": []}
    mismatch = {**match, "platforms": ["Netflix"]}
    s_match, _ = R.score_content(content, cv, {}, match)
    s_miss, _ = R.score_content(content, cv, {}, mismatch)
    assert s_match > s_miss


def test_group_score_penalises_disagreement_and_veto():
    high_agree, _ = R.group_score([0.8, 0.8, 0.8])
    low_agree, _ = R.group_score([0.95, 0.2, 0.9])  # one member hates it
    assert high_agree > low_agree
    vetoed, _ = R.group_score([0.8, 0.8, 0.8], veto_count=1)
    assert vetoed < high_agree


def test_group_min_score_matters():
    # mean is equal but min differs -> lower min should score lower
    a, _ = R.group_score([0.6, 0.6, 0.6])
    b, _ = R.group_score([0.9, 0.6, 0.3])
    assert a > b


# ---- Room winner logic (mirrors server.compute_winner math) ----
def winner_check(votes, threshold, quorum):
    total = len(votes)
    likes = votes.count("like")
    supers = votes.count("superlike")
    dislikes = votes.count("dislike")
    vetoes = votes.count("veto")
    agreement = (likes + supers) / total if total else 0
    tie = 2 * supers + likes - dislikes
    wins = agreement >= threshold and total >= quorum and vetoes == 0
    return wins, agreement, tie


def test_threshold_and_quorum():
    # 3 votes, 2 likes -> 66% agreement
    wins, agr, _ = winner_check(["like", "like", "dislike"], 0.6, 2)
    assert wins and abs(agr - 2 / 3) < 1e-9
    # fails quorum
    wins, _, _ = winner_check(["like"], 0.6, 2)
    assert not wins


def test_veto_blocks_title():
    wins, _, _ = winner_check(["superlike", "superlike", "veto"], 0.5, 2)
    assert not wins


def test_tie_breaker_score():
    _, _, tie_super = winner_check(["superlike", "superlike"], 0.5, 1)
    _, _, tie_like = winner_check(["like", "like"], 0.5, 1)
    assert tie_super > tie_like  # superlikes weigh more


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
