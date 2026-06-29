# Plan de tests — SwipeMovie (SwipeNight) seul + intégration movie-reco

> **Objectif** : liste de tests EXHAUSTIVE pour valider
> **(a)** SwipeMovie / SwipeNight seul, après corrections, et
> **(b)** son intégration dans **movie-reco** (produit commercial *licence-clean*,
> données Wikidata CC0 + Wikipedia CC BY-SA, **TMDB interdit dans le livrable**).
>
> Document complémentaire de [`INTEGRATION.md`](./INTEGRATION.md). Conventions :
> messages/doc en français ; **ne rien casser** d'existant (movie-reco : 176 tests
> verts). Chemins de référence :
> - SwipeMovie : `swipe-movie/backend/`, `swipe-movie/frontend/`.
> - movie-reco : `movie-reco/movreco/`, `movie-reco/tests/`.

## Légende d'exécution (pré-requis par test)

| Marqueur | Signification |
|---|---|
| 🟢 **OFFLINE** | Automatisable hors-ligne, sans réseau, sans Mongo, sans device. CI par défaut. |
| 🌐 **RÉSEAU** | Nécessite un accès réseau (Wikidata SPARQL / Wikipedia REST / pypi / npm). |
| 🍃 **MONGO** | Nécessite MongoDB **ou** un adaptateur en mémoire / `mongomock-motor`. |
| 📱 **DEVICE** | Nécessite un device/émulateur Expo (ou web bundler) — manuel ou e2e. |
| 🤖 **HTTP-LIVE** | Nécessite un backend SwipeNight démarré (`EXPO_PUBLIC_BACKEND_URL`) — donc Mongo + serveur up. |

Sauf mention contraire, **tout test backend `pytest` est 🟢 OFFLINE** s'il n'attaque
que des fonctions pures (recommender, licensing) ou un catalogue de fixtures.

---

## 0. Corrections pré-requises à valider (dette identifiée)

Ces points doivent être corrigés AVANT de figer la suite ; chaque correction a son
test de non-régression dédié (référencé entre crochets).

| # | Défaut constaté | Fichier | Test de validation |
|---|---|---|---|
| C1 | Docstring « 50 films + 30 series + 30 anime » mais le catalogue réel est **52 + 30 + 30 = 112** | `backend/seed_data.py` | [U-SEED-1] |
| C2 | `generate_candidates()` : filtre `formats` **inopérant** (corps = `pass`) | `backend/recommender.py` | [U-CAND-2] |
| C3 | `score_content()` inclut `exploration = random.random()` → score **non déterministe** ; `components` n'expose pas `exploration` | `backend/recommender.py` | [U-SCORE-6], [U-SCORE-7] |
| C4 | `seasons`/`episodes` via `random.randint` **sans seed** dans le seed | `backend/seed_data.py` | [U-SEED-3] |
| C5 | `quality` alimentée par `external_rating`/`vote_count` (note externe) — **piège fuite/licence** pour le produit | `backend/recommender.py` | [I-LIC-3] |
| C6 | Pénalité « déjà-vu » et « disliked » se **cumulent** sur `seen_disliked` (−0.50 + −0.70) — comportement à figer/documenter | `backend/recommender.py` | [U-PEN-3] |

> Les tests ci-dessous décrivent le comportement **attendu après correction**.
> Quand un test fige un choix discutable (ex. C6), il est annoté « décision à acter ».

---

## 1. Tests unitaires backend SwipeMovie (🟢 OFFLINE)

Cible : `backend/recommender.py`, `backend/licensing.py`, `backend/seed_data.py`.
Outils : `pytest`, fonctions pures, **aucun réseau / aucun Mongo**.
Commande : `cd swipe-movie/backend && python -m pytest tests/test_recommender.py tests/test_tmdb_licensing.py -v`

### 1.1 `recommender` — tokenisation & content vector

- **[U-CV-1]** `_tokenize()` : minuscule, ne garde que les mots `>= 4` lettres, retire
  les stopwords, **déduplique**, plafonne à **12** tokens. Vérifier ordre préservé
  et coupe à 12 sur un texte long.
- **[U-CV-2]** `_tokenize("")` / `None` → `[]`.
- **[U-CV-3]** `build_content_vector()` : 7 catégories avec préfixes `gen:`, `key:`,
  `syn:`, `cas:`, `cre:`, `stu:`, `cou:`. Vérifier que chaque préfixe correspond à
  `cat[:3]`.
- **[U-CV-4]** Poids par catégorie = `CAT_WEIGHTS[cat] / nb_tokens` ; la **somme des
  poids d'une catégorie** non vide ≈ `CAT_WEIGHTS[cat]` (à epsilon près). Somme des
  `CAT_WEIGHTS` == 1.0.
- **[U-CV-5]** `crew` inclut `creator` (un contenu avec `creator="X"` et `crew=[]`
  produit un token `cre:x`).
- **[U-CV-6]** `country_language` agrège `countries + languages`.
- **[U-CV-7]** Tous les poids du vecteur sont **non négatifs** (invariant).
- **[U-CV-8]** Catégorie vide / absente → aucun token de cette catégorie (pas de
  division par zéro).

### 1.2 `recommender` — cosine

- **[U-COS-1]** `cosine(a, a) == 1.0` pour `a` non nul.
- **[U-COS-2]** Vecteurs orthogonaux (clés disjointes) → `0.0`.
- **[U-COS-3]** `cosine({}, x)` / `cosine(x, {})` → `0.0` (garde `na/nb == 0`).
- **[U-COS-4]** Symétrie : `cosine(a, b) == cosine(b, a)`.
- **[U-COS-5]** Choix du plus petit dict pour le produit scalaire creux ne change
  pas le résultat (a plus grand que b et vice-versa).

### 1.3 `recommender` — vecteur de goût (`build_user_vector`)

- **[U-UV-1]** Signal `> 0` alimente le pôle positif, `< 0` le pôle négatif ;
  résultat = `avg(pos) − avg(neg)` (cf. test existant `test_user_vector_positive_minus_negative`).
- **[U-UV-2]** Pondération par récence : `rec = exp(-days/half_life)`, `half_life=180`.
  Une interaction ancienne pèse moins qu'une récente (même signal).
- **[U-UV-3]** Normalisation par `pos_w` / `neg_w` (et non par le nombre brut
  d'interactions).
- **[U-UV-4]** `ts` **naïf** → traité comme UTC (pas d'exception ; `tzinfo` ajouté).
- **[U-UV-5]** `signal == 0` (neutral) **ignoré** (ni pos ni neg).
- **[U-UV-6]** `content_id` absent de `content_vectors` → ignoré silencieusement.
- **[U-UV-7]** `days` borné à `>= 0` (interaction « dans le futur » → `rec <= 1`).
- **[U-UV-8]** Aucune interaction positive → pas de composante positive ; idem négatif.

### 1.4 `recommender` — qualité bayésienne (`bayesian_score`)

- **[U-BAY-1]** Contenu obscur (peu de votes, note haute) tiré vers `C` ; contenu
  populaire reste proche de sa note (cf. test existant).
- **[U-BAY-2]** `bayesian_score(C, 0) == C` (garde `(v+m)==0`… **en pratique
  `m=50` donc `v+m≠0`** ; tester explicitement `bayesian_score(R, 0) → C`).
- **[U-BAY-3]** Cas pathologique `m=0` et `v=0` → renvoie `C` (garde dédiée).
- **[U-BAY-4]** Monotonie : à votes égaux, `R` plus grand → score plus grand.

### 1.5 `recommender` — scoring individuel (`score_content`)

- **[U-SCORE-1]** Blend pondéré : taste 0.35 / collab 0.25 (constante 0.5) /
  quality 0.15 / availability 0.10 / novelty 0.05 / popularity 0.05 /
  exploration 0.05. Vérifier la **somme des poids = 1.0**.
- **[U-SCORE-2]** `has_taste=True` : `taste = clamp((cos+1)/2, 0, 1)`. `has_taste=False`
  → `taste = 0.5`.
- **[U-SCORE-3]** `availability` : aucune plateforme dans `ctx` → `0.5` ;
  intersection providers/plateformes non vide → `1.0` ; disjointe → `0.3`
  (cf. test existant `test_platform_availability_score`).
- **[U-SCORE-4]** `novelty = clamp(1 - (annee_courante - year)/50, 0, 1)` ; film
  récent > film ancien.
- **[U-SCORE-5]** `popularity = clamp(pop/100, 0, 1)`.
- **[U-SCORE-6]** *(post-correction C3)* Déterminisme : avec `exploration` neutralisé
  (seed `random` fixé ou injection d'un RNG), deux appels donnent le **même** score.
- **[U-SCORE-7]** `components` retournés contiennent
  `{taste, collab, quality, availability, novelty, popularity}` et **PAS**
  `exploration` (invariant de contrat actuel).
- **[U-SCORE-8]** `components` arrondis à 3 décimales.
- **[U-SCORE-9]** Métadonnées riches (genres + cast + overview + dispo + qualité)
  scorent plus haut que métadonnées vides (cf. test existant
  `test_recommender_uses_enriched_metadata`).

### 1.6 `recommender` — pénalités (`score_content`)

- **[U-PEN-1]** `seen_liked`/`seen_neutral` sans rewatch → `−0.50` ; avec
  `allow_rewatch=True` → **pas** de pénalité déjà-vu.
- **[U-PEN-2]** `abandoned` → `−0.80`.
- **[U-PEN-3]** `seen_disliked` → cumule `−0.50` (déjà-vu) **+** `−0.70` (disliked)
  = `−1.20`. *(décision à acter : cumul voulu ou exclusif ? — figer le comportement)*.
- **[U-PEN-4]** Genre rejeté (intersection `genres` ∩ `rejected_genres`, insensible
  à la casse) → `−0.40`.
- **[U-PEN-5]** Mood `short` + `runtime > 140` → `−0.30`.
- **[U-PEN-6]** Mood `long` + `runtime < 50` (et runtime non nul) → `−0.15`.
- **[U-PEN-7]** Aucune pénalité quand l'état n'est pas dans le `state_map`.

### 1.7 `recommender` — génération de candidats (`generate_candidates`)

- **[U-CAND-1]** Exclusions dures (`ctx["excluded"]`) retirées du pool.
- **[U-CAND-2]** *(post-correction C2)* `formats` filtre réellement
  (un contenu de type hors `formats` est exclu ou correctement géré) **OU** test qui
  documente que `formats` n'a aucun effet (comportement actuel : `pass`). Acter le choix.
- **[U-CAND-3]** `limit` respecté (pool tronqué à `limit`).
- **[U-CAND-4]** `excluded` / `formats` absents → renvoie tout le catalogue.

### 1.8 `recommender` — MMR (`mmr_rerank`)

- **[U-MMR-1]** Premier élément choisi = celui de plus forte pertinence
  (`selected` vide → `val = rel`).
- **[U-MMR-2]** `lambda=0.75` : pénalise la similarité aux déjà sélectionnés.
  Deux items quasi identiques en tête ne sont pas tous deux retenus si un item
  pertinent et **distinct** existe.
- **[U-MMR-3]** Renvoie au plus `k` éléments ; `k > len(ranked)` → renvoie tout.
- **[U-MMR-4]** `content_vectors` manquant pour un id → `cosine` vu comme `{}` →
  diversité = 0 pour cet item (pas d'exception).
- **[U-MMR-5]** Stabilité : entrée déjà triée et diverse → ordre préservé.

### 1.9 `recommender` — score de groupe (`group_score`)

- **[U-GRP-1]** `member_scores` vide → `(-999, {})`.
- **[U-GRP-2]** Formule : `0.50·moy + 0.25·min − 0.15·σ + 0.10·watchlist_bonus
  + 0.10·platform_bonus − veto_count`.
- **[U-GRP-3]** Désaccord (σ élevé) pénalise (cf. test existant).
- **[U-GRP-4]** À moyenne égale, `min` plus bas → score plus bas (cf. test existant
  `test_group_min_score_matters`).
- **[U-GRP-5]** `veto_count` réduit le score (−1.0 par veto).
- **[U-GRP-6]** Bonus watchlist / plateforme partagée augmentent le score.
- **[U-GRP-7]** `components` = `{mean_score, min_score, disagreement}` arrondis 3 déc.

### 1.10 `recommender` — explications

- **[U-EXP-1]** `similar_to_liked_content` apparaît quand des titres aimés
  partagent genres/cast/crew ; cite au plus 2 titres, triés par chevauchement.
- **[U-EXP-2]** `preferred_genre` quand intersection genres/préférences.
- **[U-EXP-3]** `available_on_platform` quand providers ∩ plateformes.
- **[U-EXP-4]** `trending` si `popularity >= 80`.
- **[U-EXP-5]** `new_release` si `year >= annee_courante - 1`.
- **[U-EXP-6]** `highly_rated` si `bayesian_score >= 7.8`.
- **[U-EXP-7]** `anime_affinity` si `type == "anime"` et `ctx.anime_affinity`.
- **[U-EXP-8]** Fallback `popularity` quand aucune autre raison.
- **[U-EXP-9]** Plafond **3** raisons.
- **[U-EXP-10]** `group_explanation` : `group_compatibility` si `min_score >= 0.55`,
  `shared_watchlist`, `available_on_platform`, fallback ; plafond 3.

### 1.11 `licensing` — matrice clé × commercial (tests existants à conserver)

Source : `tests/test_tmdb_licensing.py`. Matrice complète :

| EXTERNAL_APIS_ENABLED | TMDB_API_KEY | COMMERCIAL_MODE | LICENSE_CONFIRMED | `can_use_tmdb()` attendu | Test |
|---|---|---|---|---|---|
| true | ✗ | false | false | **False** (pas de clé) | [U-LIC-1] |
| false | ✓ | false | — | **False** (master off) | [U-LIC-2] |
| true | ✓ | false | false | **True** (beta non-comm.) | [U-LIC-3] |
| true | ✓ | true | false | **False** (comm. non licencié) | [U-LIC-4] |
| true | ✓ | true | true | **True** (comm. licencié) | [U-LIC-5] |

- **[U-LIC-6]** `tmdb_disabled_reason()` : message contient « commercial » dans le
  cas [U-LIC-4] ; `None` dans les cas autorisés.
- **[U-LIC-7]** `get_provider_status()` : shape complète
  (`tmdb_enabled`, `external_apis_enabled`, `commercial_mode`,
  `tmdb_license_confirmed`, `tmdb_key_present`, `seed_catalog_fallback`,
  `reason`, `default_country`, `default_language`) ; `seed_catalog_fallback` True ;
  `reason` non vide quand désactivé.
- **[U-LIC-8]** Helpers `_flag()` : `"1"/"true"/"yes"/"on"` (insensible casse) → True ;
  défauts (`EXTERNAL_APIS_ENABLED` défaut `true`, `COMMERCIAL_MODE` défaut `false`).
- **[U-LIC-9]** *(produit)* En **mode produit** (`COMMERCIAL_MODE=true`, aucune clé),
  `can_use_tmdb()` == False **par construction** (cf. INTEGRATION §2.2 Option A).

### 1.12 `services/external/tmdb` — dégradation gracieuse (🟢 OFFLINE)

Source : `tests/test_tmdb_licensing.py::test_tmdb_service_degrades_when_disabled`.

- **[U-TMDB-1]** TMDB désactivé : `search_movies`/`search_tv` → `[]`,
  `enrich_content_from_tmdb` → `{}`, `get_watch_providers` → `[]`. **Aucun appel
  réseau** (vérifier qu'aucun `httpx` n'est émis quand désactivé — mock/spy).
- **[U-TMDB-2]** `tmdb_enabled()` reflète `can_use_tmdb()`.
- **[U-TMDB-3]** `_quality()` du service duplique la formule bayésienne du
  recommander (même résultat pour mêmes entrées).
- **[U-TMDB-4]** `normalize_tmdb_movie` / `normalize_tmdb_tv` produisent le schéma
  SwipeNight attendu (clés `id,title,year,overview,genres,...`).
- **[U-TMDB-5]** Fallback langue overview FR→EN quand l'overview FR est vide.

### 1.13 `seed_data` (🟢 OFFLINE)

- **[U-SEED-1]** *(post-correction C1)* Cohérence docstring ↔ contenu : nombre de
  films/séries/animes annoncé == longueur réelle des listes
  (`len(MOVIES)`, `len(SERIES)`, `len(ANIME)`).
- **[U-SEED-2]** `build_catalog()` : chaque entrée a `id` **unique**, `type` ∈
  `{movie, series, anime}`, champs requis présents (`genres`, `year`, ...).
- **[U-SEED-3]** *(post-correction C4)* `seasons`/`episodes` déterministes
  (seed fixé) → catalogue **reproductible** entre deux imports.
- **[U-SEED-4]** Images picsum déterministes (même `id` → même URL).
- **[U-SEED-5]** Animes : `countries=["JP"]`, `languages=["ja"]`.

---

## 2. Tests d'API SwipeMovie (FastAPI)

Deux familles selon le besoin d'infra :

### 2.1 In-process via `TestClient` + adaptateur Mongo en mémoire (🟢 OFFLINE souhaité, 🍃 sinon)

> **Pré-requis correction** : `server.py` dépend aujourd'hui directement de
> `database.db` (Motor). Pour rendre ces tests OFFLINE, introduire un **adaptateur
> Mongo en mémoire** (dict) ou `mongomock-motor` (cf. INTEGRATION §6.1). Sans cela,
> ces tests sont 🍃 MONGO. Installer `motor`, `python-jose`, `passlib` si besoin.

- **[A-AUTH-1]** `POST /api/auth/register` : crée l'utilisateur, renvoie `token` + `user`. 🍃
- **[A-AUTH-2]** `POST /api/auth/register` email dupliqué → `400`. 🍃
- **[A-AUTH-3]** `POST /api/auth/login` identifiants valides → `200` + token ;
  préférences `onboarded`. 🍃
- **[A-AUTH-4]** `POST /api/auth/login` mauvais mot de passe → `401`. 🍃
- **[A-AUTH-5]** `GET /api/auth/me` avec token → `200` ; sans token → `401/403`. 🍃
- **[A-AUTH-6]** JWT : token expiré / signature invalide → `401`. 🟢 (test unitaire
  `auth.py` : `create_access_token` / `decode` purs, sans Mongo).
- **[A-PREF-1]** `PUT /api/users/preferences` : persiste country/platforms/formats/
  genres/moods/onboarded. 🍃
- **[A-CAL-1]** `GET /api/contents/calibration` : renvoie 15–20 titres. 🍃
- **[A-BROWSE-1]** `GET /api/contents` sans filtre : `count >= 100`. 🍃
- **[A-BROWSE-2]** `GET /api/contents?type=movie` : tous `type == "movie"`. 🍃
- **[A-BROWSE-3]** `GET /api/contents?q=a` : `count > 0` (recherche sous-chaîne). 🍃
- **[A-BROWSE-4]** `GET /api/contents?genre=...&sort=...` : filtres genre + tri. 🍃
- **[A-DET-1]** `GET /api/contents/{id}` : `content.id == id`, `match_score`,
  `reasons`, `reviews`, `community_rating`, `user_state`. 🍃
- **[A-DET-2]** `id` inexistant → `404`. 🍃
- **[A-RECO-1]** `GET /api/recommendations/home` : `hero` non nul (`match_score`,
  `reasons`), `rails >= 1`. 🍃
- **[A-RECO-2]** `GET /api/recommendations?context={general,movies,series,anime,new}`
  → `200` + `results` pour chaque contexte. 🍃
- **[A-RECO-3]** `GET /api/recommendations/{id}/reasons` → liste de raisons. 🍃
- **[A-EVT-1]** `POST /api/events {like}` puis détail → `user_state.state ==
  "seen_liked"`. 🍃
- **[A-EVT-2]** `POST /api/contents/{id}/state` : transitions d'état + recompute du
  vecteur de goût (`recompute_user_vector`). 🍃
- **[A-WL-1]** `POST /api/watchlist/{id}` puis `GET /api/watchlist` → présent. 🍃
- **[A-WL-2]** `DELETE /api/watchlist/{id}` → absent. 🍃
- **[A-REV-1]** `POST /api/reviews` (public) → visible dans
  `GET /api/contents/{id}/reviews`. 🍃
- **[A-REV-2]** Review **privée** non visible par un autre utilisateur. 🍃
- **[A-PRIV-1]** `GET /api/users/me/privacy` : défaut `history_visibility ==
  "private"`. 🍃
- **[A-PRIV-2]** `PUT /api/users/me/privacy` : modifie la visibilité. 🍃
- **[A-RGPD-1]** `DELETE` historique / compte : purge effective. 🍃

### 2.2 Rooms — vote, quorum, seuil, veto, WebSocket

Logique de vote pure (sans Mongo) déjà testée via `winner_check` dans
`tests/test_recommender.py` :

- **[A-ROOM-PURE-1]** Quorum : 1 vote pour quorum 2 → pas de gagnant. 🟢
- **[A-ROOM-PURE-2]** Seuil : 2 likes / 3 votes = 66% ≥ 60% → gagne. 🟢
- **[A-ROOM-PURE-3]** Veto bloque le titre même avec majorité. 🟢
- **[A-ROOM-PURE-4]** Tie-break : `2·superlikes + likes − dislikes`
  (superlikes pèsent plus). 🟢

Flux complet (nécessite état persistant) :

- **[A-ROOM-1]** `POST /api/rooms` : crée room, `join_code` de 6 caractères,
  `max_users <= 5`. 🍃
- **[A-ROOM-2]** `POST /api/rooms/join {join_code}` valide → rejoint ; code
  inexistant → `404` ; room pleine (5) → refus. 🍃
- **[A-ROOM-3]** `POST /api/rooms/{id}/start` (owner only) : `candidates > 0` ;
  non-owner → `403`. 🍃
- **[A-ROOM-4]** `GET /api/rooms/{id}/candidates` : triés par `group_score`,
  `reasons` présents. 🍃
- **[A-ROOM-5]** `POST /api/rooms/{id}/vote` : upsert du vote, recalcul du gagnant. 🍃
- **[A-ROOM-6]** `GET /api/rooms/{id}/result` : `winner` cohérent avec les votes
  (solo room quorum 1 + superlike → winner déterministe). 🍃
- **[A-ROOM-7]** `POST /api/rooms/{id}/relaunch` : `round` incrémenté (2), nouveaux
  candidats. 🍃
- **[A-ROOM-8]** `compute_winner` : départage par `(tie_score, agreement_rate)`. 🍃
- **[A-WS-1]** `GET /api/ws/rooms/{room_id}` : connexion WS, réception
  `room_started`, `vote_update` lors d'un vote. 🍃 + 🤖 (WS = serveur up).
- **[A-WS-2]** `broadcast` envoie à tous les membres connectés ; déconnexion gérée
  sans crash. 🍃
- **[A-WS-3]** *(charge)* 5 membres connectés votent simultanément → toutes les
  mises à jour reçues, pas de course sur `compute_winner`. 🍃 / 📱

### 2.3 Endpoints TMDB / providers (garde-fous) — 🟢 OFFLINE

- **[A-TMDB-1]** `GET /api/providers/status` reflète `get_provider_status()`. 🍃/🟢
- **[A-TMDB-2]** `/api/search` branche TMDB **désactivée** (mode produit) → ne sert
  que le catalogue local, **zéro appel réseau**. 🟢 (mock httpx en garde).
- **[A-TMDB-3]** `/api/contents/{id}/enrich`, `/api/contents/refresh-trending`,
  `/api/providers/{id}` : no-op gracieux quand TMDB désactivé (pas d'exception,
  réponse cohérente). 🍃

### 2.4 Suite HTTP-LIVE existante (🤖 HTTP-LIVE + 🍃 MONGO)

`tests/test_swipenight_api.py` cible un backend déployé via
`EXPO_PUBLIC_BACKEND_URL`. **À conserver en intégration/e2e**, marquée hors-CI
hors-ligne. Couvre auth, onboarding, recos, browse, détail, events, watchlist,
reviews, rooms (flux complet), privacy, `dev/run-daily-job`.
Commande : `EXPO_PUBLIC_BACKEND_URL=https://... python -m pytest tests/test_swipenight_api.py -v`.

---

## 3. Tests frontend SwipeMovie (Expo / React Native, TypeScript)

Cible : `frontend/src/`, `frontend/app/`. Outils actuels : **`tsc`** (typecheck),
**`expo lint`** (eslint 9). **Jest n'est pas encore configuré** → recommandé de
l'ajouter (`jest-expo` + `@testing-library/react-native`) pour les tests unitaires.

### 3.1 Statique (🟢 OFFLINE) — à mettre en CI

- **[F-TSC-1]** Typecheck strict : `npx tsc --noEmit` (0 erreur).
  Commande : `cd swipe-movie/frontend && npx tsc --noEmit`.
- **[F-LINT-1]** Lint : `npm run lint` (`expo lint`) sans erreur.
  Commande : `cd swipe-movie/frontend && npm run lint`.

### 3.2 Unitaires `src/api.ts` (🟢 OFFLINE, jest + fetch mocké)

- **[F-API-1]** `req()` : parse JSON défensif (réponse vide → pas de crash).
- **[F-API-2]** `req()` : `!res.ok` → `throw Error(detail)` (message issu du body).
- **[F-API-3]** `BASE == ${EXPO_PUBLIC_BACKEND_URL}/api`.
- **[F-API-4]** `get/post/put/del` : méthode HTTP + body JSON + header `Authorization`
  quand token présent.
- **[F-API-5]** `wsUrl()` : dérive `ws://`/`wss://` du backend (`http→ws`,
  `https→wss`).
- **[F-API-6]** Gestion du token via `storage` (clé `sn_token`, round-trip
  JSON.stringify/parse correct).

### 3.3 Unitaires `src/auth.tsx` (🟢 OFFLINE, jest + RTL)

- **[F-AUTH-1]** `login` / `register` : `POST /auth/login|register` → `setToken` +
  `setUser`.
- **[F-AUTH-2]** `logout` : efface token + user.
- **[F-AUTH-3]** `refresh` : `GET /auth/me` ; échec → token effacé.
- **[F-AUTH-4]** Bootstrap au montage (`useEffect`) ; `ready` passe à true.

### 3.4 Unitaires `src/utils/storage` (🟢 OFFLINE)

- **[F-STO-1]** Implémentations native (SecureStore/AsyncStorage) et web
  (AsyncStorage) : `get/set/remove` **never-throw** (erreur interne avalée).
- **[F-STO-2]** `secureGet` après `secureSet` → valeur d'origine (round-trip).

### 3.5 Composants (🟢 OFFLINE, jest + RTL)

- **[F-CMP-1]** `SwipeDeck` : `onSwipe(card, dir)` appelé avec la bonne direction
  (right=like, left=dislike, up=superlike, down=veto, tap=neutral).
- **[F-CMP-2]** `MatchBadge` affiche le `match_score`.
- **[F-CMP-3]** `Stars` rend la note ; `PosterCard` rend titre + affiche.
- **[F-CMP-4]** `EmptyState` / `Loader` rendus conditionnels.

### 3.6 Écrans clés (📱 DEVICE pour e2e ; 🟢 pour smoke-render RTL)

- **[F-SCR-1]** `app/index.tsx` : redirection selon `ready`/`user`/`onboarded`.
- **[F-SCR-2]** `(tabs)/index.tsx` (home) : appelle `/recommendations/home`, rails
  + hero, pull-to-refresh. 📱
- **[F-SCR-3]** `(tabs)/browse.tsx` : recherche debouncée `/search` ou `/contents`,
  filtres type/genre/sort. 📱
- **[F-SCR-4]** `room/[id].tsx` : lobby → vote → result, WebSocket temps réel. 📱
- **[F-SCR-5]** `content/[id].tsx` : détail + reviews + watchlist + BottomSheet de
  notation. 📱
- **[F-SCR-6]** `(auth)/login.tsx` : formulaire + affichage d'erreur. 🟢/📱
- **[F-SCR-7]** `onboarding/calibration.tsx` : deck de calibration → `POST /events`
  + `PUT /users/preferences`. 📱

---

## 4. Tests d'INTÉGRATION movie-reco (le cœur)

> Valident que SwipeNight, branché sur le **moteur movreco** et le **catalogue
> Wikidata/Wikipedia**, fonctionne **sans jamais toucher TMDB**. Cible :
> `swipe-movie/backend/recommender_bridge.py` (nouveau, cf. INTEGRATION §3.3) +
> `movreco.api.service`. La plupart sont 🟢 OFFLINE grâce au **catalogue
> synthétique** `movie-reco/tests/_synthetic.py` (aucun réseau, aucun modèle).

### 4.1 Bridge moteur — initialisation & catalogue

- **[I-BRG-1]** `init_engine(cfg)` charge `AppState` (items + emb + structured) une
  seule fois ; `items`/`emb` **alignés** ligne à ligne (clé = `qid`). 🟢
- **[I-BRG-2]** `id` de contenu == `qid` Wikidata (pivot d'intégration) ; aucun UUID
  mock dans le catalogue produit. 🟢
- **[I-BRG-3]** `public_content()` mappe colonnes parquet → schéma payload frontend
  (`id,title,year,overview,poster_url,genres,providers,...`) **sans changer les
  clés** attendues par `api.ts` (contrat frontend intact). 🟢
- **[I-BRG-4]** Catalogue absent / embeddings manquants → erreur claire
  (`ArtifactMissing` → 503), pas de crash. 🟢

### 4.2 Catalogue Wikidata **au lieu de** TMDB

- **[I-CAT-1]** Le catalogue chargé provient des artefacts movreco
  (`items.parquet`/`embeddings.npy`), **pas** de `seed_data.py` ni de `tmdb.py`. 🟢
- **[I-CAT-2]** `seed_data` / `tmdb` **non importés** dans le chemin produit
  (vérifier que `server.py` produit n'importe ni `seed_data` ni
  `services.external.tmdb`). 🟢 (analyse statique des imports / `importlib`).
- **[I-CAT-3]** *(catalogue réel)* `movreco ingest` (quelques années) → `synopsis`
  → `embed --backend tfidf` → `features` produit un catalogue exploitable. 🌐
  (réseau Wikidata/Wikipedia). Hors CI offline.
- **[I-CAT-4]** Backend embeddings **`tfidf`** (sans torch) suffit : pipeline
  recommend fonctionne sans sentence-transformers ni faiss (repli cosinus numpy). 🟢

### 4.3 Swipe → note → vecteur de goût (via movreco)

- **[I-TASTE-1]** Table de conversion swipe→note (INTEGRATION §4.1) :
  superlike→5.0, like→4.5, watchlist→4.0, dislike→2.0, abandoned→1.5,
  veto→**exclusion** (`exclude`, pas une note), neutral→ignoré. 🟢
- **[I-TASTE-2]** `signed_taste_vector(emb_rated, ratings)` (movreco) sur les
  embeddings : un utilisateur qui « like » le Genre 0 reçoit majoritairement du
  Genre 0 (catalogue synthétique groupé par genre). 🟢
- **[I-TASTE-3]** Récence : pré-pondération des notes par `exp(-days/180)` conserve
  l'effet récence du `build_user_vector` SwipeNight. 🟢
- **[I-TASTE-4]** Un `veto` ajoute le `qid` à `exclude` → **absent** des recos
  (exclusion dure), distinct d'une simple note basse. 🟢
- **[I-TASTE-5]** Recompute idempotent : mêmes swipes → même vecteur de goût
  (déterminisme). 🟢

### 4.4 Recommandations via le moteur movreco

- **[I-RECO-1]** `recommend_for_user(rated, n, exclude)` délègue à
  `service.recommend_from_ratings(mode="hybrid")` ; renvoie `n` films, **exclut**
  les `exclude` et les déjà notés. 🟢
- **[I-RECO-2]** Pertinence : recos dominées par le genre aimé (cf. catalogue
  synthétique) — convergence avec [I-TASTE-2]. 🟢
- **[I-RECO-3]** MMR movreco (`recommend.diversity.mmr`, λ configurable) applique la
  diversité ; remplace `mmr_rerank` SwipeNight (même algo cosinus). 🟢
- **[I-RECO-4]** Sérendipité movreco (`diversity.serendipity_picks`) remplace
  `exploration=random` → recos pertinentes mais éloignées, **déterministes**. 🟢
- **[I-RECO-5]** `aucune note valide` (qids hors catalogue) → `InvalidRequest`/422. 🟢
- **[I-RECO-6]** Le payload conserve `match_score`, `reasons`, `components` →
  frontend inchangé. 🟢
- **[I-RECO-7]** *(charge)* `n` grand borné par la taille du catalogue. 🟢

### 4.5 Room / group recommend (apport SwipeNight sur scores movreco)

- **[I-GRP-1]** `per_candidate_scores(rated, candidate_qids)` : un
  `signed_taste_vector` par membre + cosinus matriciel → score individuel par
  (membre × candidat). 🟢
- **[I-GRP-2]** `group_score()` SwipeNight **inchangé**, alimenté par les scores
  movreco : `0.5·moy + 0.25·min − 0.15·σ − vetos + bonus`. 🟢
- **[I-GRP-3]** Veto d'un membre (exclusion movreco) → `veto_count` répercuté dans
  `group_score` / candidat retiré. 🟢
- **[I-GRP-4]** `compute_winner`, vote, relaunch : **inchangés** (logique de vote
  pure) ; testés en 🍃 (§2.2). 🟢 pour la partie pure.
- **[I-GRP-5]** Perf : 5 membres × N candidats en une passe numpy (pas de boucle
  HTTP) — assertion de complexité / temps borné. 🟢

### 4.6 `/suggest` pour la calibration (apprentissage actif)

- **[I-SUG-1]** `/api/contents/calibration` appelle
  `active.suggest_to_rate` (via bridge `suggest_to_rate`/`/suggest` movreco) au lieu
  du tri populaire + shuffle. 🟢
- **[I-SUG-2]** Contrat : renvoie `{qid, label}` (cf.
  `tests/test_api_suggest.py`), **exclut** les déjà notés, sans doublon,
  **déterministe**. 🟢
- **[I-SUG-3]** Couverture : suggestions touchent plusieurs genres (farthest-point)
  → calibration plus informative que « 20 populaires aléatoires ». 🟢
- **[I-SUG-4]** Onboarding frontend (`calibration.tsx`) **inchangé** : poste
  toujours des `/events`. 📱/🟢 (contrat).

### 4.7 Cohérence des licences (AUCUN appel TMDB) — CRITIQUE

- **[I-LIC-1]** Mode produit forcé : `COMMERCIAL_MODE=true`, **aucune** clé TMDB →
  `can_use_tmdb() == False` (Option A, INTEGRATION §2.2). 🟢
- **[I-LIC-2]** **Aucun appel réseau TMDB** sur l'ensemble des parcours
  (recos, rooms, calibration, browse, détail) : spy/mock sur `httpx` vers
  `api.themoviedb.org` → **0 requête**. 🟢
- **[I-LIC-3]** *(anti-fuite, correction C5)* La qualité bayésienne du produit
  n'utilise **aucune note externe** TMDB/IMDb : composante neutralisée **ou**
  alimentée par un proxy CC0 (sitelinks Wikidata). `external_rating`/`vote_count`
  absents des features produit. 🟢
- **[I-LIC-4]** Catalogue produit : champs servis = Wikidata (CC0) ; **pas** de
  republication du texte Wikipedia brut (embeddings stockés) ; extrait de synopsis
  affiché uniquement avec attribution CC BY-SA. 🟢 (vérification de schéma/flags).
- **[I-LIC-5]** Affiches : URL Commons (P18) **ou** placeholder local ; jamais
  `image.tmdb.org` ni `picsum.photos` dans le produit. 🟢
- **[I-LIC-6]** `tmdb.py` / `seed_data.py` déplacés en extra `research`
  (non importés par défaut) ; build produit installable **sans** ces modules. 🟢
- **[I-LIC-7]** Test garde-fou conservé : `tests/test_tmdb_licensing.py` reste vert
  (le verrou commercial fonctionne). 🟢

### 4.8 Recherche & providers en mode licence-clean

- **[I-SEARCH-1]** `/api/search` : recherche sous-chaîne sur `label` du catalogue
  local **uniquement** (aucune branche TMDB). 🟢
- **[I-SEARCH-2]** *(option)* recherche live Wikidata
  (`movreco.ingest.wikidata.lookup_film`) pour catalogue extensible. 🌐
- **[I-PROV-1]** `providers` (plateformes) absents de Wikidata → `[]` ;
  `availability` movreco se neutralise proprement (0.5) — pas de crash, score
  cohérent. 🟢
- **[I-GENRE-1]** Genres Wikidata localisés (FR) : mapping/normalisation pour que
  les filtres rooms (`RoomFiltersBody`) et browse continuent de matcher. 🟢

---

## 5. Non-régression movie-reco (les 176 tests restent verts) — 🟢 OFFLINE

> **YOU MUST** : l'intégration ne touche movreco **qu'en ajout**. La suite existante
> doit rester 100% verte.

- **[NR-1]** `cd movie-reco && python -m pytest -q` → **176 passed** (collecte
  confirmée : 176 tests). 🟢
- **[NR-2]** Aucune modification de signature publique de `movreco.api.service`
  (`load_state`, `recommend_from_ratings`, `suggest_owner`, `similar`,
  `recommend_owner`) — le bridge **consomme**, ne modifie pas. 🟢
- **[NR-3]** Aucune dépendance lourde nouvelle imposée à movreco (tfidf sans torch ;
  faiss optionnel avec repli cosinus). 🟢
- **[NR-4]** Suites clés à surveiller spécifiquement (sous-ensemble représentatif) :
  `test_api.py`, `test_api_suggest.py`, `test_api_explain.py`, `test_diversity.py`,
  `test_serendipity.py`, `test_taste_vector_degenerate.py`, `test_temporal_ndcg.py`,
  `test_align_embeddings.py`, `test_embeddings_backends.py`, `test_faiss_persistence.py`. 🟢
- **[NR-5]** Pas de fuite d'état de test : les fixtures écrivent sous `tmp_path`
  (jamais dans `data/processed` réel). 🟢

---

## 6. Critères d'acceptation (Definition of Done)

**SwipeMovie seul (après corrections)**

1. `pytest swipe-movie/backend/tests/test_recommender.py` et
   `test_tmdb_licensing.py` → **verts** (incl. nouveaux tests U-*). 🟢
2. Corrections C1–C6 couvertes par un test chacune.
3. `tsc --noEmit` et `expo lint` → **0 erreur** côté frontend. 🟢
4. Tests API (§2.1/§2.2) verts via adaptateur Mongo en mémoire (ou 🍃 Mongo réel).
5. Aucune régression de contrat de payload pour le frontend.

**Intégration movie-reco (licence-clean)**

6. Tous les tests d'intégration §4 marqués 🟢 passent **hors-ligne** sur le
   catalogue synthétique.
7. **[I-LIC-2]** : **0 appel réseau TMDB** sur tous les parcours (assertion dure).
8. `can_use_tmdb() == False` en mode produit ; `tmdb.py`/`seed_data.py` non
   importés par défaut.
9. **[NR-1]** : movie-reco **176 passed** inchangé.
10. Le frontend fonctionne sans modification (mêmes endpoints / mêmes clés de
    payload) — vérifié au moins par smoke-render + un parcours 📱 manuel.

---

## 7. Commandes d'exécution (récapitulatif)

```bash
# --- Backend SwipeMovie : unitaires purs (🟢 OFFLINE) ---
cd swipe-movie/backend
python -m pytest tests/test_recommender.py tests/test_tmdb_licensing.py -v

# --- Backend SwipeMovie : API in-process (🍃 Mongo ou adaptateur mémoire) ---
# pip install motor python-jose passlib mongomock-motor   # si besoin
python -m pytest tests/ -v -k "not test_swipenight_api"

# --- Backend SwipeMovie : suite HTTP-LIVE (🤖 serveur up + 🍃 Mongo) ---
EXPO_PUBLIC_BACKEND_URL=https://<preview-url> \
  python -m pytest tests/test_swipenight_api.py -v

# --- Frontend SwipeMovie : statique (🟢 OFFLINE) ---
cd swipe-movie/frontend
npx tsc --noEmit
npm run lint
# (après ajout de jest-expo)
# npm test

# --- Intégration movie-reco : bridge + moteur (🟢 OFFLINE, catalogue synthétique) ---
pip install -e movie-reco            # rend movreco importable
cd swipe-movie/backend
python -m pytest tests/test_integration_bridge.py -v   # (à créer)

# --- Catalogue licence-clean réel (🌐 RÉSEAU Wikidata/Wikipedia) ---
cd movie-reco
movreco ingest --years 2018-2024
movreco synopsis
movreco embed --backend tfidf
movreco features

# --- Non-régression movie-reco (🟢 OFFLINE) : DOIT rester 176 verts ---
cd movie-reco
python -m pytest -q     # attendu : 176 passed
```

---

## 8. Matrice de couverture (synthèse offline / réseau / mongo / device)

| Niveau | Section | OFFLINE 🟢 | RÉSEAU 🌐 | MONGO 🍃 | DEVICE 📱 |
|---|---|:---:|:---:|:---:|:---:|
| Unitaires recommender | §1.1–§1.10 | ✅ | — | — | — |
| Unitaires licensing / tmdb-degrade / seed | §1.11–§1.13 | ✅ | — | — | — |
| API in-process (auth, browse, reco, events, watchlist, reviews) | §2.1 | ✅ (adaptateur) | — | ✅ (réel) | — |
| Rooms — logique pure | §2.2 | ✅ | — | — | — |
| Rooms — flux complet + WS | §2.2 | — | — | ✅ | (charge) |
| API TMDB garde-fous | §2.3 | ✅ | — | (partiel) | — |
| HTTP-LIVE existant | §2.4 | — | — | ✅ | — (🤖) |
| Frontend statique (tsc/eslint) | §3.1 | ✅ | (npm install) | — | — |
| Frontend unitaire (api/auth/storage/cmp) | §3.2–§3.5 | ✅ (jest) | — | — | — |
| Frontend écrans e2e | §3.6 | (smoke) | — | — | ✅ |
| Intégration bridge / catalogue synthétique | §4.1–§4.2, §4.4–§4.8 | ✅ | — | — | — |
| Intégration catalogue réel | §4.2 [I-CAT-3], §4.8 [I-SEARCH-2] | — | ✅ | — | — |
| Cohérence licences (0 appel TMDB) | §4.7 | ✅ | — | — | — |
| Non-régression movie-reco (176) | §5 | ✅ | — | — | — |
