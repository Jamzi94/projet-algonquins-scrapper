# SwipeNight 🎬🔥

A mobile-first recommendation + group-swipe app for **movies, TV series and anime**.
Inspired by Couchmoney, Trakt, Letterboxd and Tinder — but V1 is **not** a social
network. It focuses on: personalized recommendations, private multi-user rooms
where up to 5 people swipe together to pick what to watch, rich content detail
pages, ratings & simple reviews, and watchlist/status tracking.

## Stack
- **Frontend:** Expo (React Native) + expo-router — runs on iOS, Android & web.
- **Backend:** FastAPI + Motor (async MongoDB).
- **Realtime:** WebSocket for live room voting (`/api/ws/rooms/{id}`).
- **Auth:** JWT email/password with pseudonymous usernames.

## Run
Backend and frontend run under supervisor automatically. Key env vars:

### `backend/.env`
```
MONGO_URL=...           # provided
DB_NAME=...             # provided
JWT_SECRET=...          # rotate in production
TMDB_API_KEY=""         # optional
ANILIST_TOKEN=""        # optional
TRAKT_CLIENT_ID=""      # optional
```

### `frontend/.env`
```
EXPO_PUBLIC_BACKEND_URL=...   # the app calls {URL}/api
```

## External data (TMDB / AniList / Trakt)
The app ships with **mock seeded data** (50 movies, 32 series, 30 anime) so it is
fully usable offline. All external calls are abstracted behind a backend-only
service layer (`backend/services/external/tmdb.py`) and gated by
`backend/licensing.py`. The TMDB API key is **never** sent to the frontend.

### Run modes
1. **No external APIs (default offline):** leave `TMDB_API_KEY` empty. The app
   serves the seeded catalog. `GET /api/search` searches local titles only;
   `GET /api/contents/{id}/enrich` returns the content unchanged.
2. **Free non-commercial beta with TMDB:** set `TMDB_API_KEY`, keep
   `COMMERCIAL_MODE="false"`. TMDB now powers search, detail enrichment,
   trending refresh and watch providers, merged with the seed catalog.
3. **Commercial use:** set `COMMERCIAL_MODE="true"`. TMDB stays **disabled**
   (seed fallback) unless you also set `TMDB_COMMERCIAL_LICENSE_CONFIRMED="true"`
   after confirming a commercial TMDB license.

`GET /api/provider-status` reports the current mode. On boot the backend logs a
warning when TMDB is disabled and why.

### Refresh trending content
With TMDB enabled, call `POST /api/contents/refresh-trending` (dev/admin) to
upsert this week's trending movies & TV into the catalog (deduped by
`external_ids.tmdb`, then title/year/type). Returns `inserted/updated/skipped`.

### TMDB usage & attribution
- TMDB is **optional** — the app works fully without it via the seed catalog.
- Current intended mode is a **free non-commercial beta**.
- For monetization/commercial use, set `COMMERCIAL_MODE=true` and only enable
  TMDB if `TMDB_COMMERCIAL_LICENSE_CONFIRMED=true`.
- Attribution (shown in-app under Settings → Credits):
  > "This product uses the TMDB API but is not endorsed or certified by TMDB."

⚠️ **Never commit `TMDB_API_KEY`.** It is backend-only; the frontend never sees it.
No scraping is performed; platform availability is metadata only and history
import is manual/semi-manual.

### Running the tests
```
cd backend && python -m pytest tests/ -v
```
Includes recommender/room logic, TMDB licensing guardrails (key/commercial-mode
matrix), graceful service degradation when disabled, and enriched-metadata scoring.

## Recommendation engine (`backend/recommender.py`)
A hybrid, **interpretable** recommender, architected for future ML:
1. Feature store — `build_content_vector` (genres 25%, keywords 20%, synopsis
   20%, cast 15%, crew 10%, studio 5%, country/lang 5%).
2. User taste vector — recency-weighted positives minus negatives
   (`half_life = 180d`).
3. Candidate generation — whole catalog for V1 (<2000), source-mix ready.
4. Individual ranking — `0.35 taste + 0.25 collab + 0.15 quality + 0.10
   availability + 0.05 novelty + 0.05 popularity + 0.05 exploration − penalties`.
   Quality uses a **Bayesian** score so obscure titles don't dominate.
5. Group ranking — `0.50 mean + 0.25 min − 0.15 disagreement + bonuses −
   veto_penalty` (favours choices that aren't terrible for any one member).
6. Diversity re-rank — Maximal Marginal Relevance (`λ = 0.75`).
7. Explainability — every reco carries human-readable reasons.
8/9. Daily + event-driven recompute — `POST /api/dev/run-daily-job` and automatic
   cache invalidation on every important event.

`# TODO(ML)` markers show exactly where to plug a two-tower embedding model
(taste) and a trained collaborative-filtering predictor (collab).

## Rooms
Private rooms with invite code, max 5 users, owner-set threshold % + quorum.
A title wins when `agreement_rate ≥ threshold AND total_votes ≥ quorum AND
veto_count == 0`. Tie-break: `2·superlikes + likes − dislikes`. No winner → top-3
candidates + relaunch / lower-threshold / change-filter options.

## Tests
```
cd backend && python -m pytest tests/test_recommender.py -v
```
Covers recommendation scoring, Bayesian quality, veto exclusion, threshold,
quorum, group score (incl. min-score), already-seen exclusion, platform filtering,
and tie-breaker logic.

## End-to-end flow
create account → onboard (prefs + 20-title calibration) → home recommendations →
content detail → create room → invite (code) → swipe → winning title.
