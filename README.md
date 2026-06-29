# CineFeel — recommandation de films (Wikidata + TMDB)

Ce dépôt contient **deux projets qui fonctionnent en synergie** :

| Projet | Rôle | Stack |
| --- | --- | --- |
| **`movie-reco/`** | Le **moteur de recommandation** (le « cerveau ») : données libres Wikidata (CC0) + Wikipédia (CC BY-SA), embeddings sémantiques, FAISS. | Python (CLI Typer), scikit-learn (tf‑idf), FAISS, pandas |
| **`swipe-movie/`** | L'**application** « CineFeel » : un backend API + une app mobile/web de swipe (solo ou en groupe). | FastAPI + MongoDB (backend), Expo / React Native (frontend) |

L'app **délègue ses recommandations au moteur movie-reco** (via un « pont »), et peut **enrichir** le catalogue avec **TMDB** (affiches, vraies dates, synopsis) — Wikidata reste la base licence‑clean, TMDB est la couche de vérité factuelle.

---

## 1. Vue d'ensemble (comment tout s'enchaîne)

```
Wikidata (CC0) ─┐                          ┌─ TMDB (affiches, dates, synopsis, notes) [optionnel]
Wikipédia ──────┤                          │
                ▼                          ▼
   movie-reco : ingest → synopsis → embed(tf-idf) → FAISS
                          (catalogue + embeddings)
                                  │
                  recommender_bridge.py (le « pont »)
                                  ▼
   swipe-movie/backend (FastAPI)  ──►  MongoDB (comptes, swipes, rooms, catalogue servi)
                                  ▼
   swipe-movie/frontend (Expo « CineFeel »)  ──►  APK Android / Web (SPA)
```

- **Reco individuelle** : swipes de l'utilisateur → notes → *vecteur de goût* → recherche FAISS + diversité (MMR) + sérendipité.
- **Reco de groupe (rooms)** : `group_score` combine les goûts des membres.

---

## 2. `movie-reco/` — le moteur

Recommandeur **content-based** (pas de filtrage collaboratif), pensé pour le **cold‑start**.

| Élément | Rôle |
| --- | --- |
| `movreco/cli.py` | CLI Typer : `ingest` → `synopsis` → `embed` → `features` → `recommend` (+ `serve`, `tune`, `import-ratings`). |
| `movreco/config.py` + `config/config.yaml` | Configuration (bornes du catalogue, langue, tf‑idf, reco, User‑Agent Wikidata…). |
| `movreco/ingest/` | Récupération des données : `wikidata.py` (SPARQL), `synopsis.py` (Wikipédia REST), `matching.py` (appariement titres), `cache.py`, `import_ratings.py` (Letterboxd/IMDb). |
| `movreco/features/` | `embeddings.py` (tf‑idf **sans torch** par défaut), `structured.py` (genres/réalisateurs/décennie…), `combine.py` (matrice de features). |
| `movreco/recommend/` | `index.py` (**FAISS**), `diversity.py` (**MMR**, pénalité popularité, sérendipité), `pipeline.py` (orchestration), `tuning.py`. |
| `movreco/model/` | `taste_vector.py` (vecteur de goût signé — mode *mvp*, utilisé en prod), `preference.py` (**LightGBM**, mode *hybride*, optionnel), `active.py` (apprentissage actif), `evaluate.py` (NDCG). |
| `movreco/llm/` | Couche LLM optionnelle (re‑ranking/explications) — **désactivée par défaut**. |
| `movreco/api/` | API FastAPI exposant le moteur en service (usage autonome). |
| `data/` | Artefacts produits : `processed/items.parquet`, `embeddings.npy`, `structured.parquet`… (le catalogue versionné y est licence‑clean : métadonnées + **embeddings**, pas le texte brut Wikipédia). |
| `DATA_LICENSES.md` | Règles de licence (sources autorisées/interdites). |

---

## 3. `swipe-movie/backend/` — l'API (FastAPI)

| Fichier | Rôle |
| --- | --- |
| `server.py` | L'**API** : auth, profil, swipes/états, **recommandations** (home, contexte), **rooms** (création, vote, résultat), watchlist, recherche, endpoints TMDB. Au démarrage : seed du catalogue + planification de l'enrichissement TMDB. |
| `database.py` | Connexion **MongoDB** : **Motor** (vrai Mongo) si `MONGO_URL` pointe vers un serveur, sinon **mongomock-motor** (Mongo **en mémoire**, pour dev/CI). |
| `auth.py` | Authentification **JWT** (PyJWT) + hash mots de passe (passlib/bcrypt). |
| `recommender.py` | Recommander **natif** SwipeNight (vecteurs de contenu, `group_score` des rooms, score bayésien). |
| `recommender_bridge.py` | **Le pont** vers movie-reco (`SynergyEngine`) : catalogue + reco déléguée au moteur (FAISS/MMR), conversion swipes→notes, reco de room. |
| `licensing.py` | Les **interrupteurs** : `DATA_SOURCE` (wikidata/seed/tmdb), `can_use_tmdb()`, `TMDB_ENRICH`, `get_provider_status()`. |
| `seed_data.py` | Catalogue de **démonstration** (repli si movie-reco indisponible). |
| `services/external/tmdb.py` | Intégration **TMDB** (chargée **paresseusement**, seulement si TMDB actif) : recherche, affiches, dates, synopsis, notes, plateformes. |
| `requirements*.txt` | `requirements.txt` (prod), `requirements-sandbox.txt` (dev/CI : Mongo mémoire + movie-reco + dnspython pour Atlas), `requirements-tmdb.txt` (extra TMDB). |
| `SANDBOX.md` | Guide pour lancer le backend sans MongoDB ni clé. |

**Endpoints utiles** : `GET /api/provider-status` (état des sources), `POST /api/admin/reseed` (recharge le catalogue), `POST /api/contents/refresh-covers` (affiches TMDB).

---

## 4. `swipe-movie/frontend/` — l'app « CineFeel » (Expo / React Native)

| Élément | Rôle |
| --- | --- |
| `app/` | Écrans (expo-router) : `(auth)/` (login/register), `onboarding/` (préférences + calibration), `(tabs)/` (accueil, browse, watchlist, rooms, profil), `room/`, `content/[id]`, `settings`. |
| `src/api.ts` | Client HTTP vers le backend (`EXPO_PUBLIC_BACKEND_URL`). |
| `src/auth.tsx`, `src/components.tsx`, `src/theme.ts`, `src/hooks/`, `src/utils/` | État d'auth, composants UI, thème, hooks, utilitaires. |
| `app.json` | Config Expo : nom **CineFeel**, icône, `android.package`/`ios.bundleIdentifier` (`com.swipenight.app`), `owner` Expo. |
| `eas.json` | Profils **EAS Build** (preview = APK, production = AAB) + `EXPO_PUBLIC_BACKEND_URL`. |
| `assets/images/` | Icône + splash (cœur + play, dégradé violet→corail). |

**Variable clé** : `EXPO_PUBLIC_BACKEND_URL` = URL du backend (ex. l'URL Render). Sans elle, l'app ne joint pas l'API.

---

## 5. MongoDB — à quoi ça sert ici

MongoDB est la **base de données** du backend (l'app a été écrite avec, via le client async **Motor**). Elle stocke :
- **comptes** utilisateurs, **préférences**, **swipes/états** (vus, aimés, watchlist…),
- **rooms** (sessions de groupe) + **votes**,
- le **catalogue servi** (collection `contents`).

Deux modes, choisis automatiquement selon `MONGO_URL` (cf. `database.py`) :

| `MONGO_URL` | Moteur | Usage |
| --- | --- | --- |
| absent / `memory` / `mock` | **mongomock-motor** (en mémoire) | Dev / CI / démo — **données volatiles** (perdues au redémarrage). Aucun serveur requis. |
| une URI `mongodb+srv://…` | **Motor** (vrai MongoDB) | Production — **données persistantes**. |

En production on utilise **MongoDB Atlas** (offre gratuite M0) : on crée un cluster, un utilisateur, on autorise les IP (`0.0.0.0/0` car les IP Render sont dynamiques), puis on met l'URI dans `MONGO_URL` côté Render. *(`dnspython` est inclus pour résoudre les URI `mongodb+srv://`.)*

---

## 6. Render — l'hébergement du backend

[Render](https://render.com) héberge le **backend FastAPI** (le frontend, lui, est un APK ou un site statique). Le déploiement est décrit par **`render.yaml`** (Blueprint) à la racine :

- **type** : service web Python, **plan gratuit**.
- **rootDir** : `swipe-movie/backend` ; **build** : `pip install -r requirements-sandbox.txt` ; **start** : `uvicorn server:app --host 0.0.0.0 --port $PORT`.
- **healthcheck** : `/api/provider-status`.
- Déploiement : Render → New → **Blueprint** → connecter le dépôt → Apply. Render **redéploie automatiquement** à chaque push sur `main`.

⚠️ **Plan gratuit** : le service se met en **veille** après ~15 min d'inactivité (1er appel ensuite = 30‑60 s) — un workflow *keep‑alive* le ping régulièrement. Avec un gros catalogue, prévoir éventuellement le plan **Starter** (CPU/mémoire dédiés).

---

## 7. Sources de données & synergie (Wikidata / TMDB)

| Mode | Réglages (env backend) |
| --- | --- |
| **Wikidata seul** (100 % libre) | `DATA_SOURCE=wikidata` + `EXTERNAL_APIS_ENABLED=false` |
| **Les deux — synergie** (recommandé) | `DATA_SOURCE=wikidata` + `EXTERNAL_APIS_ENABLED=true` + `TMDB_API_KEY=…` + `TMDB_ENRICH=full` → catalogue Wikidata + **affiches/dates/synopsis/notes réelles TMDB** |
| **TMDB seul** | `DATA_SOURCE=tmdb` + `EXTERNAL_APIS_ENABLED=true` + `TMDB_API_KEY=…` |

> Le catalogue actuel est **unifié** (Wikidata + une grande couche TMDB), tout embeddé dans le même espace tf‑idf → **FAISS sémantique sur l'ensemble**. TMDB est facultatif et **toujours désactivable**. Attribution TMDB présente dans l'app (écran Réglages).

---

## 8. Variables d'environnement (backend)

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `MONGO_URL` | Connexion Mongo (URI Atlas, ou `memory`). | `memory` |
| `DB_NAME` | Nom de la base. | `swipenight` |
| `JWT_SECRET` | Secret de signature JWT. | *(à définir)* |
| `DATA_SOURCE` | `wikidata` \| `seed` \| `tmdb`. | `wikidata` |
| `EXTERNAL_APIS_ENABLED` | Active/désactive TMDB. | `false` |
| `TMDB_API_KEY` | Clé API TMDB. | *(vide)* |
| `TMDB_ENRICH` | `full` (affiche + date + note + synopsis) \| `covers`. | `full` |
| `RESEED_ON_START` | `1` = recharge tout le catalogue au démarrage (puis à retirer). | *(absent)* |

---

## 9. Lancer, tester, déployer, builder

- **Backend en local (sans rien installer de lourd)** : voir `swipe-movie/backend/SANDBOX.md`.
- **Tests & CI** : `.github/workflows/ci.yml` (backend pytest + frontend tsc/export + non‑régression movie-reco). `swipe-movie/TESTS.md`.
- **Construire l'APK / le site web** : `.github/workflows/eas-build.yml` (EAS Build cloud) + `swipe-movie/BUILD.md`.
- **Keep‑alive Render** : `.github/workflows/keepalive.yml`.
- **Intégration des deux projets** : `swipe-movie/INTEGRATION.md`.
- **Moteur movie-reco** : `movie-reco/README.md` + `movie-reco/ROADMAP.md`.

---

## 10. Licences

- **Wikidata** : CC0. **Wikipédia** : CC BY‑SA (on stocke des **embeddings**, pas le texte brut).
- **TMDB** : optionnel, soumis aux conditions TMDB (attribution requise — présente dans l'app). Voir `movie-reco/DATA_LICENSES.md`.
