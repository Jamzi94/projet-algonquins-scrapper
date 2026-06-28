# SwipeNight — Product Requirements & Build Log

## Original Problem Statement
Production-ready MVP mobile app for personalized movie/TV/anime recommendations + private
multi-user rooms (up to 5) that swipe Tinder-style to choose what to watch. Detailed content
pages, ratings & simple reviews, watchlist/status tracking, hybrid interpretable recommendation
engine, email/password JWT auth with pseudonymous usernames, WebSocket realtime room voting,
mock seeded data (works without external API keys). NOT a social feed in V1.

## Stack & Architecture
- Frontend: Expo (React Native) + expo-router (file-based routing), reanimated/gesture-handler swipe deck, expo-blur glassmorphism, @gorhom/bottom-sheet, Fraunces+Satoshi fonts. Dark "Luxe" theme.
- Backend: FastAPI + Motor (MongoDB). Modules: server.py (API + WS + seeding), recommender.py (engine), auth.py (JWT/bcrypt), seed_data.py (catalog), database.py.
- Realtime: WebSocket /api/ws/rooms/{id} broadcasts vote/start/relaunch.
- Data: 112 seeded titles (50 movies, 32 series, 30 anime), 5 fake users, 1 demo room (code MOVIE1).

## User Personas
- Solo viewer wanting tailored recommendations across formats.
- Friend group (2–5) deciding what to watch together tonight via swipe + vote.

## Core Requirements (static)
Onboarding (prefs + 20-title calibration) · Home recommendations (carousels) · Browse w/ filters ·
Content detail (match score, explanation, cast, trailer, providers, reviews) · Ratings+reviews
(stars, reaction, spoiler, visibility) · Watchlist + 7 content states · Rooms (invite code, threshold,
quorum, veto, relaunch, group ranking) · Privacy (private by default, delete history/account) ·
Hybrid recommender (content vector, user taste vector, Bayesian quality, MMR diversity, group score,
explainability, daily + event recompute).

## Implemented (2026-06-27) — MVP COMPLETE
- ✅ JWT email/password auth + pseudonymous usernames
- ✅ Onboarding preferences + 20-card swipe calibration feeding the engine
- ✅ Home hero + rails (Recommended / On your platforms / New / Anime) with match % + reasons
- ✅ Browse (search, type/genre tabs, sort) 2-col grid
- ✅ Content detail: backdrop, match badge, "why this" reasons, meta, cast, trailer, providers, community rating, reviews, state buttons (liked/disliked/abandoned/neutral/exclude), watchlist, Rate&Review bottom sheet
- ✅ Events update state + recompute user vector + invalidate cache
- ✅ Reviews with reaction/spoiler/visibility (private/friends/public)
- ✅ Rooms: create (threshold/quorum/filters), join by code, lobby (members+code), owner start → group-ranked candidates, swipe-vote deck, winner computation (agreement≥threshold ∧ votes≥quorum ∧ no veto, tie-break 2·super+like−dislike), top-3 fallback, relaunch / lower threshold, WebSocket live updates
- ✅ Privacy settings (defaults private), delete history, delete account
- ✅ Daily job endpoint caches top_100/top_50 contexts per user
- ✅ Recommender: feature weights, recency-weighted taste vector (half_life 180d), Bayesian quality, individual score blend + penalties, MMR (λ=0.75), group score, explanations
- ✅ 10 pure-function validation tests + 30 API integration tests all pass
- ✅ README with setup, env vars, TMDB/AniList/Trakt key instructions, ML TODO markers

## Sprint — TMDB integration & licensing guardrails (2026-06-27)
- Added `backend/licensing.py` (`can_use_tmdb`, `is_commercial_mode`, `get_provider_status`): free non-commercial beta by default; TMDB allowed only when key present AND (COMMERCIAL_MODE=false OR TMDB_COMMERCIAL_LICENSE_CONFIRMED=true).
- Added backend-only `backend/services/external/tmdb.py` (search/details/credits/videos/providers/trending + normalize movie/tv + enrich). httpx, timeouts, safe error handling, fr-FR→en-US fallback. Key never exposed to frontend.
- New endpoints: `GET /api/search`, `GET /api/contents/{id}/enrich`, `POST /api/contents/refresh-trending`, `GET /api/providers/{id}`, `GET /api/provider-status`. All degrade to the seed catalog when TMDB is disabled. Startup logs a warning with the disable reason.
- Recommender consumes enriched fields (genres/cast/crew/overview/vote_average/vote_count/providers/popularity/year) with no formula change; feature vectors rebuilt on upsert/enrich.
- Frontend (minimal): Browse uses `/api/search` + rating/platform badges; Content detail auto-enriches on open + discreet "Data source" row; Settings adds Credits/data-sources (TMDB attribution) + Developer status.
- `.env.example` added; README expanded (run modes, commercial mode, attribution, refresh-trending, tests). 49 backend tests pass (19 pure + 30 integration). bcrypt<4 pin left as optional polish.

## Backlog / Remaining (prioritized)
- P1: Wire real TMDB/AniList/Trakt service layer behind existing abstractions (keys → upsert in `# TODO(external)`).
- P1: Replace placeholder collab_score with trained collaborative-filtering model (`# TODO(ML)`).
- P2: WebSocket JWT handshake; split server.py into routers; fix reviews N+1 author lookup.
- P2: Manual history import flows (Netflix/Disney+/Prime) — currently placeholders.
- P2: Friends/follows + friends' ratings on detail page.
- P3: Pin bcrypt<4 to silence passlib warning; Fraunces web font static-serve polish.

## Next Tasks
1. Add TMDB key + implement live metadata ingestion service.
2. Build collaborative-filtering data pipeline (user_vectors/content_vectors tables are ready).
