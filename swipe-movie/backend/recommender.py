"""
SwipeNight — Hybrid Recommendation Engine (V1, interpretable scoring).

This module is intentionally pure-python and side-effect free so it can be unit
tested in isolation and later swapped for an ML-backed implementation.

Pipeline (see README):
  1. Data ingestion        -> handled by seed_data.py / external services
  2. Feature store         -> build_content_vector()
  3. Candidate generation  -> generate_candidates()
  4. Individual ranking    -> score_content()
  5. Group ranking         -> group_score()
  6. Diversity re-ranking  -> mmr_rerank()
  7. Explanation           -> generate_explanations()
  8/9. Daily + event recompute -> orchestrated in server.py

# TODO(ML): replace cosine taste_score with a learned two-tower embedding model,
# and replace the constant collab_score with a trained matrix-factorization /
# implicit-ALS prediction. The feature/user vectors here are the bridge.
"""

import math
import random
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Feature weights (content vector category contribution)
# ---------------------------------------------------------------------------
CAT_WEIGHTS = {
    "genre": 0.25,
    "keyword": 0.20,
    "synopsis": 0.20,
    "cast": 0.15,
    "crew": 0.10,
    "studio": 0.05,
    "country_language": 0.05,
}

# Numeric signal strength per interaction (used to build the user taste vector)
EVENT_WEIGHTS = {
    "superlike": 5,
    "like": 3,
    "rating_5": 5,
    "rating_4": 3,
    "watchlist": 2,
    "neutral": 0,
    "dislike": -3,
    "abandoned": -4,
    "veto": -8,
}

STATE_SIGNAL = {
    "seen_liked": 3,
    "seen_disliked": -3,
    "seen_neutral": 0,
    "abandoned": -4,
    "watchlist": 2,
    "not_seen": 0,
    "excluded_from_recommendations": 0,
}

# Individual score blend
SCORE_WEIGHTS = {
    "taste": 0.35,
    "collab": 0.25,
    "quality": 0.15,
    "availability": 0.10,
    "novelty": 0.05,
    "popularity": 0.05,
    "exploration": 0.05,
}

HALF_LIFE_DAYS = 180
MMR_LAMBDA = 0.75
BAYES_C = 6.8   # global average rating (0-10 scale)
BAYES_M = 50    # minimum votes threshold

_STOPWORDS = set(
    "the a an and or of to in on for with his her their its is are was were be "
    "by from as at that this it he she they who whom which when while into out "
    "after before about between against during over under not no but you your we"
    .split()
)


def _tokenize(text):
    if not text:
        return []
    words = re.findall(r"[a-zA-Z]+", text.lower())
    seen, out = set(), []
    for w in words:
        if len(w) < 4 or w in _STOPWORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= 12:
            break
    return out


# ---------------------------------------------------------------------------
# Content vector
# ---------------------------------------------------------------------------
def build_content_vector(content):
    """Build a sparse bag-of-features vector (token -> weight) for a content."""
    vec = {}

    def add(tokens, cat):
        tokens = [t for t in (tokens or []) if t]
        if not tokens:
            return
        w = CAT_WEIGHTS[cat] / len(tokens)
        for t in tokens:
            key = f"{cat[:3]}:{str(t).lower().strip()}"
            vec[key] = vec.get(key, 0.0) + w

    add(content.get("genres"), "genre")
    add(content.get("keywords"), "keyword")
    add(_tokenize(content.get("overview", "")), "synopsis")
    add(content.get("cast"), "cast")
    crew = content.get("crew") or []
    if content.get("creator"):
        crew = crew + [content["creator"]]
    add(crew, "crew")
    add(content.get("studios"), "studio")
    add((content.get("countries") or []) + (content.get("languages") or []),
        "country_language")
    return vec


def cosine(a, b):
    if not a or not b:
        return 0.0
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(v * big.get(k, 0.0) for k, v in small.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# User taste vector
# ---------------------------------------------------------------------------
def build_user_vector(interactions, content_vectors, half_life=HALF_LIFE_DAYS):
    """
    user_vector = recency-weighted avg of positive content vectors
                  minus recency-weighted avg of negative content vectors.
    `interactions`: list of {content_id, signal(float), ts(datetime)}
    """
    pos, neg = {}, {}
    pos_w, neg_w = 0.0, 0.0
    now = datetime.now(timezone.utc)
    for it in interactions:
        cv = content_vectors.get(it["content_id"])
        if not cv:
            continue
        ts = it["ts"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days = max(0, (now - ts).days)
        rec = math.exp(-days / half_life)
        signal = it["signal"]
        if signal > 0:
            wgt = signal * rec
            for k, v in cv.items():
                pos[k] = pos.get(k, 0.0) + v * wgt
            pos_w += wgt
        elif signal < 0:
            wgt = abs(signal) * rec
            for k, v in cv.items():
                neg[k] = neg.get(k, 0.0) + v * wgt
            neg_w += wgt
    # On construit le vecteur de goût indépendamment des deux branches :
    # la partie positive et la partie négative sont chacune appliquées si
    # elles existent. Ainsi, un utilisateur qui n'a QUE des dislikes
    # (pos_w == 0) obtient bien un vecteur négatif au lieu d'un vecteur vide.
    uv = {}
    if pos_w > 0:
        for k, v in pos.items():
            uv[k] = uv.get(k, 0.0) + (v / pos_w)
    if neg_w > 0:
        for k, v in neg.items():
            uv[k] = uv.get(k, 0.0) - (v / neg_w)
    return uv


# ---------------------------------------------------------------------------
# Quality (Bayesian-adjusted rating)
# ---------------------------------------------------------------------------
def bayesian_score(R, v, C=BAYES_C, m=BAYES_M):
    if (v + m) == 0:
        return C
    return (v / (v + m)) * R + (m / (v + m)) * C


# ---------------------------------------------------------------------------
# Individual scoring
# ---------------------------------------------------------------------------
def score_content(content, content_vector, user_vector, ctx):
    """
    ctx keys:
      platforms(list), country(str), moods(list), rejected_genres(set),
      state_map(dict content_id->state), excluded(set content_ids),
      preferred_genres(list), has_taste(bool)
    Returns (score, components_dict).
    """
    cid = content["id"]

    # taste
    if ctx.get("has_taste"):
        cos = cosine(user_vector, content_vector)
        taste = max(0.0, min(1.0, (cos + 1) / 2))
    else:
        taste = 0.5

    collab = 0.5  # TODO(ML): replace with learned CF prediction

    quality = bayesian_score(content.get("external_rating", 6.8),
                             content.get("vote_count", 0)) / 10.0

    # availability
    platforms = set(ctx.get("platforms") or [])
    provs = set(content.get("providers") or [])
    if not platforms:
        availability = 0.5
    elif provs & platforms:
        availability = 1.0
    else:
        availability = 0.3

    # novelty (recent content scores slightly higher)
    year = content.get("year") or 2000
    novelty = max(0.0, min(1.0, 1 - (datetime.now().year - year) / 50))

    popularity = max(0.0, min(1.0, (content.get("popularity", 0) or 0) / 100))
    # Exploration déterministe : on dérive un bruit reproductible à partir de
    # l'id du contenu (Random seedé par l'id) au lieu de random.random() global,
    # afin de garantir des recommandations stables/reproductibles tout en
    # conservant l'esprit du signal (un « jitter » propre à chaque contenu).
    exploration = random.Random(str(cid)).random()

    score = (
        SCORE_WEIGHTS["taste"] * taste
        + SCORE_WEIGHTS["collab"] * collab
        + SCORE_WEIGHTS["quality"] * quality
        + SCORE_WEIGHTS["availability"] * availability
        + SCORE_WEIGHTS["novelty"] * novelty
        + SCORE_WEIGHTS["popularity"] * popularity
        + SCORE_WEIGHTS["exploration"] * exploration
    )

    # penalties
    state = ctx.get("state_map", {}).get(cid)
    rewatch = ctx.get("allow_rewatch", False)
    if state in ("seen_liked", "seen_disliked", "seen_neutral") and not rewatch:
        score -= 0.50
    if state == "abandoned":
        score -= 0.80
    if state == "seen_disliked":
        score -= 0.70
    rej = ctx.get("rejected_genres") or set()
    if rej and (set(g.lower() for g in content.get("genres", [])) & rej):
        score -= 0.40
    moods = set(ctx.get("moods") or [])
    rt = content.get("runtime") or 0
    if "short" in moods and rt > 140:
        score -= 0.30
    if "long" in moods and rt and rt < 50:
        score -= 0.15

    components = {
        "taste": round(taste, 3),
        "collab": round(collab, 3),
        "quality": round(quality, 3),
        "availability": round(availability, 3),
        "novelty": round(novelty, 3),
        "popularity": round(popularity, 3),
    }
    return score, components


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------
# Correspondance pluriel/singulier entre les formats de filtre et le type de
# contenu. On gère les variantes courantes pour rester robuste et rétro-compatible.
_FORMAT_ALIASES = {
    "movies": "movie",
    "movie": "movie",
    "films": "movie",
    "film": "movie",
    "series": "series",
    "serie": "series",
    "tv": "series",
    "shows": "series",
    "show": "series",
    "anime": "anime",
    "animes": "anime",
}


def _normalize_format(value):
    """Normalise un format (pluriel) ou un type de contenu (singulier) vers une
    clé canonique singulière. Renvoie la valeur minuscule inchangée si inconnue."""
    if not value:
        return ""
    key = str(value).strip().lower()
    return _FORMAT_ALIASES.get(key, key)


def generate_candidates(contents, ctx, limit=2000):
    """
    For the V1 catalog (<2000 titles) we use the whole catalog as the candidate
    pool, but we still honour hard exclusions. For larger catalogs this is where
    ANN retrieval / per-source sampling (30% similar-to-liked, 25% CF-ready,
    15% new releases, 10% popularity, 10% watchlist, 10% exploration) plugs in.
    """
    excluded = ctx.get("excluded") or set()
    # Les formats de préférence/filtre sont stockés au pluriel ("movies",
    # "series", "anime") alors que le type d'un contenu est au singulier
    # ("movie", "series", "anime"). On normalise donc chaque format vers le
    # type de contenu correspondant pour que le filtre soit réellement
    # comparable (sinon "movies" != "movie" exclurait tout le catalogue).
    formats = {_normalize_format(f) for f in (ctx.get("formats") or []) if f}
    out = []
    for c in contents:
        if c["id"] in excluded:
            continue
        # Filtre formats appliqué pour de vrai : si une liste de formats est
        # fournie, on ne garde que les contenus dont le type correspond.
        if formats and _normalize_format(c.get("type")) not in formats:
            continue
        out.append(c)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Diversity re-ranking (Maximal Marginal Relevance)
# ---------------------------------------------------------------------------
def mmr_rerank(ranked, content_vectors, k, lam=MMR_LAMBDA):
    """`ranked`: list of (content, relevance_score) sorted desc. Returns top-k."""
    selected = []
    pool = list(ranked)
    while pool and len(selected) < k:
        best_i, best_val = 0, -1e9
        for i, (c, rel) in enumerate(pool):
            if not selected:
                val = rel
            else:
                cv = content_vectors.get(c["id"], {})
                max_sim = max(
                    cosine(cv, content_vectors.get(s["id"], {})) for s in selected
                )
                val = lam * rel - (1 - lam) * max_sim
            if val > best_val:
                best_val, best_i = val, i
        selected.append(pool.pop(best_i)[0])
    return selected


# ---------------------------------------------------------------------------
# Group recommendation
# ---------------------------------------------------------------------------
def group_score(member_scores, shared_watchlist_bonus=0.0,
                shared_platform_bonus=0.0, veto_count=0):
    """member_scores: list of individual scores (one per voting member)."""
    if not member_scores:
        return -999, {}
    n = len(member_scores)
    mean = sum(member_scores) / n
    mn = min(member_scores)
    var = sum((s - mean) ** 2 for s in member_scores) / n
    disagreement = math.sqrt(var)
    veto_penalty = 1.0 * veto_count
    gs = (
        0.50 * mean
        + 0.25 * mn
        - 0.15 * disagreement
        + 0.10 * shared_watchlist_bonus
        + 0.10 * shared_platform_bonus
        - veto_penalty
    )
    return gs, {
        "mean_score": round(mean, 3),
        "min_score": round(mn, 3),
        "disagreement": round(disagreement, 3),
    }


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------
def generate_explanations(content, ctx):
    """Return a list of {code, text} reasons for an individual recommendation."""
    reasons = []
    genres = [g for g in content.get("genres", [])]
    pref_genres = set(g.lower() for g in (ctx.get("preferred_genres") or []))
    matched = [g for g in genres if g.lower() in pref_genres]

    liked_titles = ctx.get("liked_titles") or []
    # similar_to_liked_content: titles sharing the most genres/cast/crew
    best = []
    cset = set(g.lower() for g in genres) | set(
        x.lower() for x in (content.get("cast", []) + (content.get("crew") or [])))
    scored_likes = []
    for lt in liked_titles:
        lset = set(g.lower() for g in lt.get("genres", [])) | set(
            x.lower() for x in (lt.get("cast", []) + (lt.get("crew") or [])))
        overlap = len(cset & lset)
        if overlap > 0:
            scored_likes.append((overlap, lt["title"]))
    scored_likes.sort(reverse=True)
    best = [t for _, t in scored_likes[:2]]
    if best:
        reasons.append({
            "code": "similar_to_liked_content",
            "text": "Recommended because you liked " + " and ".join(best) + ".",
        })

    if matched:
        reasons.append({
            "code": "preferred_genre",
            "text": f"Matches your taste for {', '.join(matched[:2])}.",
        })

    platforms = set(ctx.get("platforms") or [])
    provs = [p for p in (content.get("providers") or []) if p in platforms]
    if provs:
        reasons.append({
            "code": "available_on_platform",
            "text": "Available on " + " and ".join(provs[:2]) + ".",
        })

    if (content.get("popularity", 0) or 0) >= 80:
        reasons.append({"code": "trending", "text": "Trending right now."})

    if (content.get("year") or 0) >= datetime.now().year - 1:
        reasons.append({"code": "new_release", "text": "Fresh new release."})

    if bayesian_score(content.get("external_rating", 0),
                      content.get("vote_count", 0)) >= 7.8:
        reasons.append({"code": "highly_rated",
                       "text": "Highly rated by the community."})

    if content.get("type") == "anime" and ctx.get("anime_affinity"):
        reasons.append({"code": "anime_affinity",
                       "text": "Picked for your love of anime."})

    if not reasons:
        reasons.append({"code": "popularity",
                       "text": "Popular pick to get you started."})
    return reasons[:3]


def group_explanation(member_count, comp, shared_watchlist, shared_platforms):
    reasons = []
    if comp.get("min_score", 0) >= 0.55:
        reasons.append({
            "code": "group_compatibility",
            "text": f"Good group match: all {member_count} members have a high predicted score.",
        })
    if shared_watchlist:
        reasons.append({
            "code": "shared_watchlist",
            "text": f"Suggested because {shared_watchlist} member(s) have it in their watchlist.",
        })
    if shared_platforms:
        reasons.append({
            "code": "available_on_platform",
            "text": "Available on platforms your group owns.",
        })
    if not reasons:
        reasons.append({
            "code": "group_compatibility",
            "text": "A balanced choice for the whole group.",
        })
    return reasons[:3]
