# SwipeNight — backend en SANDBOX (Mongo mémoire + synergie movie-reco)

Ce guide explique comment faire tourner le backend FastAPI **sans serveur
MongoDB** et **sans clé externe**, grâce à un Mongo **en mémoire** et au moteur
de recommandation **movie-reco** (catalogue Wikidata CC0 + synopsis Wikipedia
CC BY-SA). Il décrit aussi comment basculer vers un **vrai MongoDB** quand on
en a un.

Tout est **additif et rétro-compatible** : aucun comportement de production
n'est modifié. Si vous fournissez les variables d'environnement habituelles,
le backend se comporte exactement comme avant.

---

## 1. Pourquoi un Mongo « en mémoire » ?

Le backend a été écrit avec **Motor** (le client async de MongoDB), avec des
appels du type `db.users.find_one(...)`, `db.user_events.insert_one(...)`, etc.
La sandbox ne dispose **d'aucun serveur `mongod`**.

Solution : [`mongomock-motor`](https://pypi.org/project/mongomock-motor/), un
faux Mongo **en mémoire** qui expose **exactement la même API asynchrone** que
Motor. Le code applicatif (`server.py`, `auth.py`) **n'a pas à changer** : il
importe toujours `client` et `db` depuis `database.py`.

`database.py` choisit automatiquement le moteur :

| `MONGO_URL`                                   | Moteur utilisé                          |
| --------------------------------------------- | --------------------------------------- |
| absent / `""` / `memory` / `mock` / `memory://` | **mongomock-motor** (Mongo en mémoire)  |
| une vraie URI (ex. `mongodb://localhost:27017`) | **Motor** (vrai MongoDB)                |

Dans les deux cas, les exports `client` et `db` et leur API restent identiques.
Au démarrage, un log indique clairement le mode actif (mémoire vs réel).

> Note : le Mongo en mémoire est **volatil** — les données disparaissent à
> l'arrêt du process. C'est voulu : parfait pour les démos et les tests.

---

## 2. Installation (sandbox)

Depuis `swipe-movie/backend/` :

```bash
pip install -r requirements-sandbox.txt
```

Ce fichier installe le strict nécessaire : `fastapi`, `uvicorn`, `httpx`,
`PyJWT`, `passlib`, `bcrypt==4.0.1`, `email-validator`, `python-dotenv`,
`motor`, `mongomock-motor`, et le moteur **movie-reco** en mode éditable
(`-e ../../movie-reco`, backend tfidf, **sans torch**).

> `movie-reco` est le dossier **frère** de `swipe-movie` (deux niveaux au-dessus
> de `backend/`). Le pont `recommender_bridge.py` l'ajoute aussi à `sys.path`
> automatiquement ; l'installation éditable rend simplement `movreco` importable
> partout.

---

## 3. Configuration

Copiez l'exemple puis ajustez si besoin :

```bash
cp .env.example .env
```

Pour le mode sandbox, **laissez `MONGO_URL` commenté** (Mongo en mémoire). Les
valeurs par défaut suffisent :

| Variable          | Défaut sandbox | Rôle                                                        |
| ----------------- | -------------- | ----------------------------------------------------------- |
| `MONGO_URL`       | *(commenté)*   | Absent -> Mongo en mémoire ; une URI -> vrai Mongo.         |
| `DB_NAME`         | `swipenight`   | Nom de la base.                                             |
| `JWT_SECRET`      | *(à définir)*  | Secret de signature des JWT (auth.py / PyJWT).              |
| `DATA_SOURCE`     | `wikidata`     | **Interrupteur unifié** : `wikidata` (movie-reco) \| `seed` \| `tmdb`. |
| `CATALOG_SOURCE`  | *(dérivé)*     | Avancé : `movreco`\|`seed`. Prime sur `DATA_SOURCE` si défini. |
| `RECO_VIA_BRIDGE` | *(dérivé)*     | Avancé : `1`\|`0`. Prime sur `DATA_SOURCE` si défini.        |

`DATA_SOURCE` est le réglage recommandé : `wikidata` -> catalogue movie-reco + reco
via le pont ; `seed` -> catalogue démo + reco native ; `tmdb` -> base seed enrichie
par TMDB (si TMDB activé) + reco native. Les deux variables avancées restent là pour
un contrôle fin et la rétro-compatibilité.

Sans `.env` du tout, le backend démarre quand même en mode sandbox (mémoire +
movreco) ; pensez tout de même à définir un `JWT_SECRET` sérieux.

---

## 4. Lancer le backend

Depuis `swipe-movie/backend/` :

```bash
uvicorn server:app --reload --port 8000
```

Au démarrage, le log de `database.py` confirme :

```
MongoDB en MÉMOIRE (mongomock-motor) — DB_NAME='swipenight'. Aucun serveur mongod requis. ...
```

---

## 5. Passer en VRAI MongoDB

Il suffit de pointer `MONGO_URL` vers un serveur réel, par exemple dans `.env` :

```dotenv
MONGO_URL=mongodb://localhost:27017
DB_NAME=swipenight
```

`database.py` bascule alors automatiquement sur **Motor** (`AsyncIOMotorClient`).
Aucune autre modification : le code applicatif est strictement le même. C'est le
**comportement de production** d'origine.

---

## 6. Synergie avec movie-reco

La sandbox ne se contente pas de faire tourner l'API : elle l'alimente avec un
**catalogue réel, licence-clean** et un **moteur de recommandation** issus de
movie-reco.

- **Catalogue** (`CATALOG_SOURCE=movreco`, défaut) : le pont
  `recommender_bridge.py` (`SynergyEngine`) charge l'état movie-reco déjà produit
  sous `movie-reco/data` (~60 films Wikidata CC0 + synopsis Wikipedia CC BY-SA).
  Alternative : `CATALOG_SOURCE=seed` pour le catalogue de démonstration interne.
- **Recommandation** (`RECO_VIA_BRIDGE=1`, défaut) : les endpoints de reco
  délèguent au moteur movreco (TF-IDF, **sans torch**). Les *rooms*
  multi-utilisateurs réutilisent en plus `recommender.group_score` de SwipeNight.
  Mettez `RECO_VIA_BRIDGE=0` pour utiliser uniquement le recommander natif.

movie-reco n'est **jamais modifié** par le backend (ses 176 tests restent verts) :
le pont utilise seulement son API publique.

### TMDB reste activable/désactivable

TMDB n'est **pas** une source de catalogue de base : il **enrichit** seulement,
et reste **toggleable** via `licensing.can_use_tmdb()`. Variables concernées :
`EXTERNAL_APIS_ENABLED`, `TMDB_API_KEY`, `COMMERCIAL_MODE`,
`TMDB_COMMERCIAL_LICENSE_CONFIRMED`. Sans clé ou avec `EXTERNAL_APIS_ENABLED=false`,
le backend fonctionne entièrement sur movie-reco — aucun appel externe requis.

**Isolation (import paresseux).** Le module `services/external/tmdb.py` (et sa
dépendance réseau `httpx`) n'est chargé que lorsque TMDB est réellement actif —
`server.py` l'importe via `_tmdb()` à la demande. Sur le chemin licence-clean
Wikidata (défaut), TMDB n'est jamais importé. C'est une dépendance **optionnelle**
(voir `requirements-tmdb.txt`) ; pour activer TMDB : `DATA_SOURCE=tmdb` + une
`TMDB_API_KEY` valide (et `TMDB_COMMERCIAL_LICENSE_CONFIRMED=true` en mode commercial).

---

## 7. Récapitulatif rapide

```bash
# 1. Dépendances (Mongo mémoire + movie-reco)
pip install -r requirements-sandbox.txt

# 2. Config (laisser MONGO_URL commenté = mémoire)
cp .env.example .env

# 3. Lancer
uvicorn server:app --reload --port 8000

# Pour un vrai Mongo : décommenter/définir MONGO_URL dans .env
```
