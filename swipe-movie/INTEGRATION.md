# Plan d'intégration — SwipeMovie (SwipeNight) dans movie-reco

> **Cible** : produit commercial **licence-clean**. Données du produit
> **uniquement** Wikidata (CC0) + Wikipedia (CC BY-SA). TMDB **interdit** dans le
> livrable.
> **Source** : SwipeMovie / SwipeNight (app Expo/RN + backend FastAPI/MongoDB).
>
> Ce document décrit comment marier l'**expérience** SwipeMovie (swipe, rooms,
> reviews, watchlist, onboarding) avec le **moteur + les données licence-clean**
> de movie-reco, sans casser l'existant (movie-reco : **176 tests verts**).

Chemins de référence :
- movie-reco : `movie-reco/movreco/` (paquet), `movie-reco/movreco/api/` (FastAPI).
- SwipeMovie : `swipe-movie/backend/` (FastAPI/MongoDB), `swipe-movie/frontend/` (Expo).

---

## 1. Vision

L'app intégrée — nom de travail **SwipeNight (édition libre)** — conserve
**toute l'UX de SwipeMovie** :

- Deck de swipe Tinder-like (`frontend/src/components.tsx > SwipeDeck` :
  right=like, left=dislike, up=superlike, down=veto, tap=neutral).
- **Rooms multi-joueurs** (jusqu'à 5) avec vote temps réel WebSocket
  (`server.py` : `/api/rooms/*`, `/api/ws/rooms/{room_id}`).
- Pages détail, **reviews/ratings**, **watchlist**, **onboarding** (préférences +
  calibration 20 titres : `frontend/.../onboarding/calibration.tsx`).
- Auth JWT (`backend/auth.py`).

Mais elle change de **fondations** :

- Le **catalogue** ne provient plus de TMDB ni du seed mock : il vient du pipeline
  movie-reco (Wikidata métadonnées CC0 + synopsis Wikipedia CC BY-SA, stockés
  sous forme d'**embeddings** plutôt que de texte brut — cf. CLAUDE.md).
- Le **scoring individuel** (taste, similarité, MMR, sérendipité, apprentissage
  actif) est délégué au moteur movie-reco (`movreco.recommend.pipeline`,
  `movreco.model.taste_vector`, `movreco.model.active`,
  `movreco.recommend.diversity`).
- Le **scoring de groupe (rooms)** reste l'apport propre de SwipeMovie
  (`recommender.group_score`), mais alimenté par les scores individuels movie-reco.

Résultat : une app sociale de swipe/rooms, **commercialisable**, sans dette de
licence, qui réutilise le moteur déjà testé de movie-reco.

---

## 2. Résolution des licences (le cœur du sujet)

### 2.1 Ce qui doit DISPARAÎTRE du livrable

| Élément SwipeMovie | Décision | Raison |
|---|---|---|
| `backend/services/external/tmdb.py` | **Retiré** du build commercial (déplacé dans un extra `dev`/`research`, non importé par défaut). | TMDB interdit dans le produit (DATA_LICENSES.md, `.claude/rules/data-sources.md`). |
| Endpoints `server.py` qui touchent TMDB : `/api/search` (branche TMDB), `/api/contents/{id}/enrich`, `/api/contents/refresh-trending`, `/api/providers/{id}` (branche TMDB), `upsert_content()` source=tmdb | **Réécrits** pour ne jamais appeler TMDB ; `/search` et `/providers` servent uniquement le catalogue local. | Idem. |
| `backend/seed_data.py` (catalogue mock + images picsum) | **Retiré** du produit ; conservé éventuellement pour les tests unitaires hors-ligne (fixtures), jamais comme catalogue livré. | Données inventées, non sourcées ; non représentatif. |
| Images `picsum.photos` | Remplacées par les **affiches Wikidata (P18 / Commons)** quand disponibles, sinon placeholder neutre généré localement. | Commons = licences libres vérifiables. |
| Champs `external_rating` / `vote_count` issus de TMDB | Recalculés **sans note externe propriétaire** : pas de note moyenne TMDB/IMDb dans les features (piège « fuite » de CLAUDE.md). Utiliser un proxy de popularité Wikidata (sitelinks) pour la qualité bayésienne, ou neutraliser la composante. | Conformité + anti-fuite. |

### 2.2 Sort de `backend/licensing.py`

`licensing.py` est **logiquement correct** (`can_use_tmdb()` verrouille TMDB en
mode commercial). Deux options :

- **Option A (recommandée pour le produit)** : **forcer le mode commercial** et
  ne JAMAIS livrer de clé TMDB. `can_use_tmdb()` renvoie alors toujours `False`
  → tout le chemin TMDB est mort par construction. On **garde** `licensing.py`
  comme garde-fou défensif et comme source de `get_provider_status()` (devient
  un statut « source = wikidata/wikipedia, tmdb=disabled »). Le test
  `tests/test_tmdb_licensing.py` reste pertinent (vérifie que TMDB est bien
  bloqué en commercial).
- **Option B (build minimal)** : supprimer `licensing.py` + `tmdb.py` + tests
  associés et retirer l'import dans `server.py`. Plus simple, mais on perd le
  garde-fou explicite. **À éviter** : garder le verrou est plus sûr pour un
  produit qui pourrait, plus tard, ré-autoriser TMDB sous licence payante.

> Décision : **Option A**. On verrouille, on ne supprime pas. La couche TMDB
> devient un module optionnel hors du chemin produit (extra `pip install .[research]`).

### 2.3 La nouvelle source du catalogue

Le catalogue du produit = sortie du pipeline movie-reco :

```
movreco ingest   (Wikidata SPARQL, CC0)        -> data/processed/items.parquet
movreco synopsis (Wikipedia REST, CC BY-SA)    -> data/raw/synopsis.parquet
movreco embed    (tfidf OU sentence-transformers) -> data/processed/embeddings.npy (+ _ids.json)
movreco features                                -> data/processed/structured.parquet
```

`items.parquet` colonnes (cf. `ingest/wikidata.fetch_items_metadata` &
`features/structured.build_structured_features`) :
`qid, label, date, popularity (sitelinks), genres|, directors|, countries|,
cast|, keywords|, languages|, duration, imdb`.

**Important conformité** : on **ne republie pas** le texte Wikipedia brut. Le
backend SwipeMovie sert des champs Wikidata (CC0) + un **embedding** ; un extrait
de synopsis n'est exposé qu'avec attribution CC BY-SA si on choisit de l'afficher
(sinon on n'affiche que des métadonnées CC0). Voir §6 « pièges ».

---

## 3. Architecture cible

### 3.1 Répartition des responsabilités

```
┌──────────────────────────┐         ┌───────────────────────────────────┐
│  Frontend Expo/RN        │  HTTP   │  Backend SwipeNight (FastAPI/Mongo) │
│  (inchangé : api.ts,     │ ◄─────► │  server.py : auth, users, swipes,   │
│   SwipeDeck, rooms, ...)  │  + WS   │  rooms, reviews, watchlist, WS      │
└──────────────────────────┘         │                                     │
                                      │   recommender_bridge.py  ───────┐   │
                                      └─────────────────────────────────┼───┘
                                                                        │ in-process (import)
                                                            ┌───────────▼───────────────┐
                                                            │  Moteur movreco (paquet)   │
                                                            │  recommend.pipeline        │
                                                            │  model.taste_vector        │
                                                            │  model.active              │
                                                            │  recommend.diversity (MMR, │
                                                            │     sérendipité)           │
                                                            │  api.service.AppState      │
                                                            └───────────┬───────────────┘
                                                                        │ lecture artefacts
                                                            ┌───────────▼───────────────┐
                                                            │ items.parquet / emb.npy /  │
                                                            │ structured.parquet (RO)    │
                                                            │ = catalogue licence-clean  │
                                                            └────────────────────────────┘
```

- **Frontend** : zéro changement de contrat (mêmes endpoints `/api/...`,
  `api.ts` intact). On conserve `match_score`, `reasons`, `components`,
  `group_score` dans les payloads → l'UI (MatchBadge, rails, raisons) marche
  sans toucher au TS.
- **Backend SwipeNight** : reste propriétaire de **l'état utilisateur**
  (MongoDB) : `users`, `user_content_states`, `user_events`, `reviews`,
  `watchlist`, `rooms`, `room_members`, `room_votes`, `room_candidates`,
  WebSocket. Il **n'embarque plus de moteur de scoring local** : il délègue.
- **Moteur movreco** : importé **en process** (pas d'appel réseau interne ;
  movie-reco charge ses artefacts une fois, comme `api/service.load_state`). Le
  catalogue (items/emb/structured) est **lu seule fois** au démarrage et partagé.

### 3.2 Où vit quoi

| Donnée | Lieu | Source de vérité |
|---|---|---|
| Catalogue (titres, métadonnées, embeddings) | Fichiers parquet/npy movie-reco, chargés en RAM (`AppState`) | Wikidata/Wikipedia (pipeline movreco) |
| Identité, swipes, états, reviews, watchlist | **MongoDB SwipeNight** | SwipeNight |
| Rooms, membres, votes, candidats | **MongoDB SwipeNight** | SwipeNight |
| Vecteur de goût utilisateur | **calculé à la volée** par movreco depuis les swipes Mongo (cache Mongo `user_vectors` optionnel) | dérivé |

L'**`id` de contenu devient le `qid` Wikidata** (`Qxxxxx`). On supprime les UUID
de contenu mock. Les collections Mongo qui référencent `content_id` stockent
désormais un `qid`. C'est le **pivot d'intégration** (cf. §4).

### 3.3 Comment SwipeNight appelle movreco

Nouveau module **`swipe-movie/backend/recommender_bridge.py`** (remplace l'usage
direct de `recommender.py` dans `server.py`). Il encapsule l'état movreco et
expose des fonctions alignées sur les besoins de `server.py` :

```python
# recommender_bridge.py  (esquisse)
from movreco.config import load_config
from movreco.api import service as movreco_service   # réutilise AppState + load_state
from movreco.recommend.pipeline import recommend as movreco_recommend
from movreco.model import active

_STATE = None  # movreco_service.AppState, chargé une fois

def init_engine(cfg=None):
    global _STATE
    _STATE = movreco_service.load_state(cfg or load_config())
    return _STATE

def recommend_for_user(rated, *, n, exclude, serendipity=0.0):
    """rated: [(qid, rating)]  ->  [{qid, label, score}] via le pipeline movreco."""
    qids   = [q for q, _ in rated]
    ratings= [r for _, r in rated]
    eff, results = movreco_service.recommend_from_ratings(
        _STATE, [{"qid": q, "rating": r} for q, r in rated],
        mode="hybrid", n=n, exclude=exclude)
    return results

def per_candidate_scores(rated, candidate_qids):
    """Score individuel par film pour les rooms (group_score a besoin d'un score
       par membre et par candidat)."""
    # taste vector signé une fois, cosinus sur les candidats (réutilise
    # model.taste_vector.signed_taste_vector + cosine_scores).

def suggest_to_rate(rated_qids, n):
    return movreco_service.suggest_owner_like(_STATE, rated_qids, n)  # cf. model.active
```

**Pourquoi en-process plutôt que deux FastAPI séparés ?**

- Les rooms ont besoin du **score individuel de CHAQUE membre pour CHAQUE
  candidat** (`server.generate_room_candidates`). Faire ça via HTTP vers l'API
  movreco multiplierait les allers-retours (membres × candidats). En-process =
  un seul `signed_taste_vector` par membre + un produit matriciel cosinus.
- movreco est un **paquet pip installable** (`pip install -e movie-reco`), donc
  l'import est trivial et garde la conformité (aucune copie de code).
- L'API FastAPI movreco (`movreco.api.app`) **reste** pour le cas
  mono-utilisateur / outils / tests ; on ne la fusionne pas. On réutilise sa
  **couche service** (`movreco.api.service`), pas son serveur HTTP.

> Variante future possible (si on veut séparer les déploiements) : exposer un
> `/recommend/batch` et un `/score/batch` sur l'API movreco et appeler en HTTP.
> Non retenu en V1 (latence rooms).

---

## 4. Mapping des concepts (le « dictionnaire » d'intégration)

| Concept SwipeMovie | Équivalent movie-reco | Notes d'intégration |
|---|---|---|
| `content["id"]` (UUID mock) | `qid` Wikidata | **Pivot**. `content_id` Mongo = `qid`. |
| `recommender.build_content_vector()` (bag-of-features pondéré, 7 catégories) | **embedding** `emb` (tfidf/sentence-transformers) aligné sur `items` | On **remplace** le content vector par l'embedding movreco. Le bag-of-features devient inutile dans le produit (gardé seulement pour la diversité textuelle des rooms si besoin). |
| `recommender.build_user_vector()` (moyenne pondérée récence pos − neg) | `model.taste_vector.signed_taste_vector(emb_rated, ratings)` | Convergence directe. Différence : movreco pondère par `(note − note_moyenne)`, SwipeMovie par signal×récence. On **mappe les signaux de swipe en notes** (cf. ligne suivante) et on laisse movreco faire le vecteur signé. La récence peut être conservée en pré-pondérant les notes. |
| Signaux de swipe : superlike/like/neutral/dislike/veto/abandoned/watchlist (`STATE_SIGNAL`, `EVENT_WEIGHTS`) | **notes** `rating ∈ [0..5]` (entrée du pipeline movreco) | Table de conversion (cf. §4.1). veto → exclusion dure (`exclude`), pas seulement note basse. |
| `score_content()` blend (taste/collab/quality/avail/novelty/pop/explo + pénalités) | `pipeline.recommend` (cosinus/​modèle supervisé + `diversity.popularity_penalty` + `novelty_scores`) | On **remplace** le blend SwipeMovie par le scoring movreco. `collab=0.5` constant disparaît (movreco n'a pas de CF ; cohérent avec « pas de filtrage collaboratif »). Les **pénalités d'état** (déjà-vu, disliked, abandoned, genre rejeté, moods) restent utiles → on les ré-applique côté bridge en post-traitement sur le score movreco, OU via `exclude`. |
| `quality = bayesian_score(external_rating, vote_count)` | proxy popularité Wikidata (sitelinks) | **Pas de note externe** (anti-fuite). Soit on neutralise la composante qualité, soit on l'alimente avec un proxy CC0. |
| `generate_candidates()` (tout le catalogue) | retrieval FAISS dans `pipeline.recommend` (top `candidates`) | movreco fait un vrai retrieval ANN → meilleure montée en charge que « tout le catalogue ». |
| `mmr_rerank(lam=0.75)` | `recommend.diversity.mmr` (lam configurable, défaut 0.7) | Même algorithme (MMR par cosinus). On garde celui de movreco (testé, basé embeddings). |
| sérendipité (absente côté SwipeMovie, juste `exploration=random`) | `diversity.serendipity_picks` + `cfg.recommend.serendipity` | **Gain net** : on remplace le bruit aléatoire par une vraie sérendipité (pertinent mais éloigné du goût). |
| `group_score()` (rooms : 0.5·moy + 0.25·min − 0.15·σ − vetos + bonus) | **conservé tel quel** (apport SwipeMovie) | Alimenté par `per_candidate_scores()` du bridge (scores individuels movreco par membre). C'est la recommandation **multi-utilisateur** que movreco n'a pas → vraie valeur ajoutée. |
| `generate_explanations()` / `group_explanation()` | `movreco.llm.rerank` (optionnel) + raisons structurées | On garde les raisons SwipeMovie (rapides, déterministes, déjà affichées par l'UI). Le LLM movreco reste optionnel et désactivé par défaut. |
| Calibration onboarding (20 titres populaires, `/contents/calibration`) | `model.active.suggest_to_rate` (apprentissage actif, farthest-point sampling) | **Remplacement qualitatif** : au lieu de 20 titres « populaires aléatoires », on propose les titres qui couvrent le mieux l'espace des goûts → calibration plus informative. Exposé via `/suggest` movreco. |

### 4.1 Table de conversion swipe → note movreco

| Geste / état SwipeMovie | `signal` actuel | Note movreco proposée | Action |
|---|---|---|---|
| superlike | +5 | 5.0 | note positive |
| like / seen_liked | +3 | 4.5 | note positive |
| watchlist | +2 | 4.0 (signal faible) | note positive, poids moindre |
| neutral / seen_neutral | 0 | (ignoré) | pas de note |
| dislike / seen_disliked | −3 | 2.0 | note négative |
| abandoned | −4 | 1.5 | note négative |
| veto | −8 | — | **exclusion dure** (`exclude=[qid]`), pas une note |
| rating explicite (1–5) | ±3..5 | rating tel quel | note directe |

La récence (`HALF_LIFE_DAYS=180`, `exp(-days/half_life)`) est conservée en
multipliant l'écart `(note − moyenne)` par le facteur de récence avant
`signed_taste_vector`, OU en gardant `build_user_vector` côté bridge mais sur les
**embeddings movreco** au lieu des content vectors (plus simple : `build_user_vector`
est agnostique à la nature du vecteur tant que `content_vectors[qid]` existe).

---

## 5. Plan par étapes (incrémental, faible risque)

> Principe : **ne rien casser**. movie-reco garde ses 176 tests verts à chaque
> étape (on n'y touche qu'en ajout). SwipeNight migre derrière des drapeaux.

### Étape 0 — Socle & catalogue (0.5–1 j)
- `pip install -e movie-reco` dans l'environnement du backend SwipeNight (movreco
  devient importable). Vérifier conflits de versions (numpy/pandas : SwipeNight
  pandas 3.0.3 / numpy 2.4.6 — voir §6).
- Générer un **petit catalogue licence-clean** : `movreco ingest` (quelques
  années) → `synopsis` → `embed --backend tfidf` (pas de torch) → `features`.
  Artefacts sous `movie-reco/data/processed/`.
- **Bascule** : on a un `items.parquet` + `embeddings.npy` réels et conformes.

### Étape 1 — Bridge moteur, mode mono-utilisateur (1–2 j)
- Créer `backend/recommender_bridge.py` (init en-process de `AppState`).
- Brancher `/api/recommendations`, `/api/recommendations/home`, `/api/contents`
  (sort=recommended) sur le bridge → scoring movreco. **Drapeau**
  `RECO_ENGINE=movreco|legacy` pour rollback instantané.
- `content_id` devient `qid`. Charger les `CONTENTS` depuis `items.parquet`
  (au lieu de `db.contents`). `public_content()` mappe les colonnes parquet vers
  le schéma de payload attendu par le frontend (cf. §4, garder les clés
  existantes pour ne pas toucher au TS).
- **Bascule** : le home feed et les recos individuelles sortent du moteur
  licence-clean. Le frontend ne voit aucune différence de contrat.

### Étape 2 — Swipes → notes → vecteur de goût (1 j)
- Dans `record_event` / `set_state` (`server.py`), convertir le signal en note
  (table §4.1) et alimenter le bridge. `recompute_user_vector` appelle
  `signed_taste_vector` / `build_user_vector` sur les embeddings movreco.
- veto → ajout à un set `excluded` (déjà géré par `build_user_context`), passé
  en `exclude` au pipeline.
- **Bascule** : le goût personnel pilote réellement les recos via movreco.

### Étape 3 — Calibration = apprentissage actif (0.5 j)
- `/api/contents/calibration` appelle `active.suggest_to_rate` (via bridge /
  `/suggest`) au lieu du tri populaire + shuffle.
- Onboarding (`onboarding/calibration.tsx`) inchangé côté UI : il poste toujours
  des `/events`.
- **Bascule** : onboarding plus informatif, toujours licence-clean.

### Étape 4 — Rooms sur scores movreco (1–2 j)
- `generate_room_candidates` : pour chaque membre, `per_candidate_scores()` du
  bridge (taste vector movreco + cosinus). `group_score()` **inchangé**.
- `compute_winner`, vote WS, relaunch : **inchangés** (logique de vote pure).
- **Bascule** : rooms multi-joueurs alimentées par le moteur licence-clean.

### Étape 5 — Démantèlement TMDB / seed (0.5–1 j)
- Réécrire `/api/search` (catalogue local uniquement, recherche sous-chaîne sur
  `label`, + option : `movreco.ingest.wikidata.lookup_film` pour recherche live
  Wikidata si on veut un catalogue extensible à la demande).
- Retirer imports `seed_data`, `tmdb` du chemin par défaut ; déplacer
  `tmdb.py`/`seed_data.py` derrière extra `research` (tests only).
- Forcer `COMMERCIAL_MODE=true`, aucune clé TMDB → `can_use_tmdb()==False`.
  `get_provider_status()` renvoie « source=wikidata/wikipedia ».
- **Bascule** : plus aucune dépendance TMDB/mock dans le produit. **Licence-clean.**

### Étape 6 — Affiches & attribution (0.5 j)
- Affiches via Wikidata P18 → URL Commons (licence libre). Placeholder local
  sinon. Bandeau d'attribution CC BY-SA si un extrait de synopsis est affiché.
- **Bascule** : conformité visuelle complète.

### Étape 7 — Durcissement (continu)
- Ajouter des tests d'intégration côté SwipeNight (bridge) **réutilisant** le
  catalogue de test movreco (fixtures parquet), MongoDB mocké (cf. §6).
- Garder `tests/test_tmdb_licensing.py` (vérifie le verrou commercial).
- CI : exécuter `pytest` movie-reco (176) **et** la suite SwipeNight.

**Effort total estimé : ~6–9 jours-personne.** Points de bascule = fin des
étapes 1 (recos), 4 (rooms), 5 (licence-clean réelle).

---

## 6. Risques & pièges

1. **MongoDB indisponible dans cet environnement.** Le bridge moteur (movreco)
   ne dépend PAS de Mongo → testable seul. Pour la partie SwipeNight :
   - V1 : abstraire l'accès via `database.py` et fournir un **adaptateur en
     mémoire** (dict) pour les tests / le dev hors-ligne ; brancher Mongo réel en
     prod. `mongomock-motor` est une alternative pour les tests async.
   - Ne pas bloquer l'intégration moteur sur la dispo Mongo.

2. **Alignement embeddings (contrat movreco).** `emb` doit rester aligné ligne à
   ligne sur `items` ; toujours passer par `features.combine.feature_matrix` et
   `align_embeddings` (déjà géré par `service.load_state`). Ne jamais réordonner
   `items` sans réindexer `emb`. Le `qid` est la clé d'alignement.

3. **Anti-fuite de données (CLAUDE.md).** Ne PAS injecter de note moyenne externe
   (TMDB/IMDb) dans les features ni dans la qualité bayésienne. Le `external_rating`
   du seed disparaît ; qualité = proxy popularité Wikidata (sitelinks) ou
   composante neutralisée. C'est aussi une exigence de licence (pas de données
   TMDB dans le produit).

4. **CC BY-SA Wikipedia.** Stocker des **embeddings**, pas le texte brut. Si un
   synopsis est affiché, attribution + lien + mention partage à l'identique.
   Privilégier l'affichage de métadonnées CC0 (Wikidata) côté UI.

5. **Conflits de dépendances.** SwipeNight épingle pandas 3.0.3 / numpy 2.4.6 ;
   movie-reco utilise pandas/numpy + (optionnel) faiss/sentence-transformers.
   Installer movreco en `[.]` (sans extras lourds) et **backend embeddings
   `tfidf`** (sans torch) pour rester léger. Vérifier que faiss est optionnel :
   `pipeline.recommend` peut fonctionner sur `build_index`/`build_or_load` ;
   prévoir un repli cosinus pur-numpy si faiss absent (déjà partiellement présent
   via `cosine_scores`).

6. **Performances rooms.** group_score = membres × candidats. Mitigation :
   - 1 retrieval FAISS commun (union des goûts) pour borner les candidats ;
   - 1 `signed_taste_vector` par membre, puis cosinus matriciel (numpy) sur le
     sous-ensemble de candidats → O(membres × candidats × dim) en une passe.
   - Cache `room_candidates` Mongo déjà prévu (persisté par round).

7. **Realtime WebSocket.** `WSManager` est **en mémoire d'un seul process**. Si
   on scale horizontalement, prévoir un bus (Redis pub/sub). En V1 mono-process,
   inchangé. Le moteur en-process n'affecte pas le WS (lecture seule, rapide).

8. **Mobile / contrat frontend.** Ne PAS changer les clés de payload
   (`match_score`, `reasons`, `components`, `group_score`, `content.{id,title,
   year,overview,poster_url,genres,providers,...}`). Le frontend (`api.ts`,
   `components.tsx`, écrans) reste **inchangé**. `content.id == qid` est
   transparent pour le client (chaîne opaque). `providers` (plateformes) n'existe
   pas dans Wikidata → renvoyer `[]` ou le déduire d'une source libre ;
   l'availability movreco se neutralise proprement (0.5) si vide.

9. **Catalogue restreint au départ.** Le pipeline Wikidata est plus lent à
   constituer qu'un seed instantané. Démarrer petit (quelques milliers de titres
   populaires par sitelinks), élargir par lots de QID (`fetch_items_metadata`).

10. **Genres/plateformes hétérogènes.** Les filtres rooms (`RoomFiltersBody`) et
    l'UI browse utilisent des libellés de genres ; Wikidata renvoie des libellés
    localisés (FR). Prévoir une normalisation/mapping de genres pour que les
    filtres existants continuent de matcher.

---

## Annexe — endpoints & fonctions réels touchés

**SwipeNight (`swipe-movie/backend/server.py`)** — adaptés :
`/api/recommendations`, `/api/recommendations/home`,
`/api/recommendations/{id}/reasons`, `/api/contents` (sort=recommended),
`/api/contents/{id}`, `/api/contents/calibration`, `/api/search`,
`/api/events`, `/api/contents/{id}/state`, `/api/watchlist*`,
`/api/rooms/{id}/start|vote|relaunch|candidates|result`, `compute_winner`,
`generate_room_candidates`, `build_user_context`, `load_feature_store`,
`recompute_user_vector`, `public_content`, `upsert_content`.

**SwipeNight — retirés du produit** : `services/external/tmdb.py`,
`seed_data.py` (→ extra `research`/fixtures), branches TMDB de `/api/search`,
`/api/contents/{id}/enrich`, `/api/contents/refresh-trending`,
`/api/providers/{id}`. `licensing.py` **conservé** (verrou, Option A).

**SwipeNight — ajouté** : `backend/recommender_bridge.py`.

**movie-reco (réutilisé, NON modifié)** :
`movreco.api.service` (`load_state`, `AppState`, `recommend_from_ratings`,
`suggest_owner`, `similar`), `movreco.recommend.pipeline.recommend`,
`movreco.model.taste_vector` (`signed_taste_vector`, `cosine_scores`),
`movreco.model.active.suggest_to_rate`,
`movreco.recommend.diversity` (`mmr`, `serendipity_picks`, `novelty_scores`,
`popularity_penalty`), `movreco.ingest.wikidata` (catalogue / recherche live),
`movreco.features.embeddings` (backend `tfidf`).
