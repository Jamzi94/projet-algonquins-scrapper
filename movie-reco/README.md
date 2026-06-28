# movreco

Recommandeur de films **personnel** à partir de ta liste de films notés, sans dépendre de TMDB.
Données libres pour usage commercial : **Wikidata** (CC0) pour les métadonnées, **Wikipedia**
(CC BY-SA, via l'API REST ; DBpedia non utilisé pour l'instant) pour les synopsis. Voir `DATA_LICENSES.md`.

Approche : mono-utilisateur en cold-start, donc *content-based + apprentissage de préférence supervisé*,
avec retrieval par embeddings sémantiques. Cible hybride construite en deux temps (MVP embeddings d'abord).

## Installation
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # optionnel, seulement si tu actives la couche LLM
```

## Préparer ta liste
Copie l'exemple et remplace par tes vraies notes :
```bash
cp data/input/ratings.example.csv data/input/ratings.csv
```
Format : `title,year,rating` (échelle au choix, ex. 0-10 ; reste cohérent).

## Pipeline
```bash
movreco ingest                 # apparie ta liste a Wikidata + construit le catalogue
movreco synopsis               # recupere les synopsis Wikipedia
movreco embed                  # calcule les embeddings
movreco features               # features structurees (genres, realisateurs, ...)
movreco train                  # entraine le modele de preference (mode hybride)
movreco recommend --mode hybrid   # ou --mode mvp pour la version embeddings seule
movreco suggest --n 10         # films a noter en priorite (apprentissage actif)
movreco evaluate               # MAE leave-one-out + NDCG@k (split temporel)
movreco tune                   # balaie une grille d'hyperparametres (recall@k)
```
Artefacts dans `data/processed/` et `models/`. Vérifie `data/processed/matching_report.csv`
après l'ingestion (l'appariement titre/année est imparfait).

### Synopsis : texte intégral ou résumé
Par défaut (`synopsis.full_text: true`), `movreco synopsis` récupère le **texte intégral**
de l'article Wikipédia (API `action=query&prop=extracts&explaintext`), tronqué à
`synopsis.max_chars` (6000 par défaut), pour des embeddings plus riches. Mettre
`synopsis.full_text: false` revient au résumé (lead) seul, comportement historique.

### Features structurées enrichies
`movreco features` produit, en plus des genres / réalisateurs / pays / décennie, des
features multi-hot pour les **acteurs** (`actor__`, P161), les **mots-clés** (`kw__`, P921)
et les **langues d'origine** (`lang__`, P364), ainsi qu'une feature numérique de **durée**
(`duration_min`). Le nombre d'acteurs et de mots-clés conservés est réglable via
`features.top_actors` (300) et `features.top_keywords` (100). Ces colonnes sont
rétro-compatibles : un catalogue qui ne fournit pas ces métadonnées produit exactement
les mêmes features qu'avant.

### Sérendipité contrôlée
`recommend.serendipity` (0.2 par défaut, plage `[0, 1]`) réserve une fraction du top-N à
des films **pertinents mais éloignés** du goût (forte nouveauté = faible cosinus au vecteur
de goût) ; le reste du top-N suit la sélection MMR habituelle. À `0.0`, aucun changement
par rapport au comportement de base.

### Apprentissage actif (films à noter en priorité)
`movreco suggest --n 10` propose les films dont la notation apporterait le plus
d'information : échantillonnage du point le plus éloigné sur les embeddings (couvre
l'espace des goûts plutôt que des doublons proches de ce qui est déjà noté), en excluant
les films déjà notés. `active.lambda_pop` (0.0 par défaut) permet de pondérer par la
popularité pour rester sur des films plus connus.

## Performance et évaluation
- **Cache réseau** : les requêtes Wikidata (SPARQL) et Wikipedia (synopsis) sont mises en
  cache sur disque sous `data/cache/` (clé = hash du contenu). Relancer `ingest`/`synopsis`
  ne retouche pas le réseau pour ce qui est déjà connu. Configurable via le bloc `cache`
  de `config.yaml` (`enabled`, `dir`) ; supprimer le dossier vide le cache.
- **Index FAISS persistant** : `recommend` réutilise l'index sauvegardé dans
  `models/catalog.faiss` s'il est compatible (même nombre de vecteurs), sinon il le
  reconstruit et le réécrit. Plus de reconstruction systématique à chaque reco.
- **NDCG@k temporel** : `evaluate` affiche, en plus de la MAE leave-one-out, un NDCG@k
  sur découpage temporel (entraînement sur les films les plus anciens, évaluation du
  classement sur les plus récents). Réglable via `evaluate.ndcg_k` et
  `evaluate.holdout_frac` ; affiché « indisponible » si trop peu de films notés.

### Tuning des hyperparamètres
`movreco tune` balaie une grille d'hyperparamètres de recommandation pour trouver les
réglages qui maximisent le **recall@k**. Le principe : on cache une fraction des films
**aimés** (notes au-dessus de la médiane), on relance le pipeline sur le reste, puis on
mesure combien des films cachés reviennent dans le top-k (recall@k) et leur qualité de
classement (ndcg@k). Chaque combinaison de la grille est évaluée puis le tableau est
classé par recall@k décroissant.

```bash
movreco tune                       # grille de config.yaml (bloc tune)
movreco tune --k 10 --holdout 0.3  # surcharge k et la fraction cachée
```

La grille se règle dans `config.yaml`, bloc `tune.grid` (`mmr_lambda`, `serendipity`,
`popularity_penalty`, `candidates`) ; `tune.k` et `tune.holdout_frac` fixent les valeurs
par défaut. Si le bloc est absent, une grille par défaut raisonnable est utilisée. Les
réglages gagnants peuvent ensuite être reportés dans le bloc `recommend` de la config.

## API

Le moteur est exposable en service HTTP via **FastAPI**. Idée maîtresse : `POST /recommend`
rend le moteur *stateless* et multi-utilisateur — un client poste **ses** notes et reçoit
des recommandations sans réentraîner (le vecteur de goût est calculé à la volée, mode `mvp`).
`GET /recommend` utilise les notes persistées du propriétaire (`rated.parquet`, mode `hybrid`
si un modèle est disponible). Les artefacts sont chargés **une seule fois au démarrage**.

```bash
pip install -e ".[api]"     # installe fastapi + uvicorn
movreco serve               # lance l'API sur http://127.0.0.1:8000
movreco serve --host 0.0.0.0 --port 8080 --reload   # options
```

Documentation interactive auto-générée (Swagger) : http://127.0.0.1:8000/docs

### Endpoints

- `GET /health` — état du service et artefacts chargés.
- `GET /movies?q=<texte>&limit=20` — recherche un film par sous-chaîne du titre
  (insensible à la casse) ; sans `q`, renvoie les premiers items.
- `GET /movies/{qid}` — fiche détaillée d'un film (404 si inconnu).
- `GET /movies/{qid}/similar?n=10` — films voisins par similarité cosinus des embeddings.
- `POST /recommend` — recommandations à partir de notes fournies dans le corps (stateless).
  Mode `mvp` par défaut ; `hybrid` se replie sur `mvp` si aucun modèle n'est chargé
  (le champ `mode` de la réponse reflète le mode réellement utilisé). Champ optionnel
  `explain: true` : si la couche LLM est activée (`llm.enabled`), une justification
  textuelle est attachée à chaque résultat (champ optionnel `raison`). Sans `llm.enabled`,
  l'option est ignorée silencieusement (aucune erreur, pas de `raison`).
- `GET /recommend?mode=hybrid&n=10` — recommandations à partir des notes persistées du
  propriétaire (`rated.parquet`).
- `GET /suggest?n=10` — films à noter en priorité (apprentissage actif) : couvre l'espace
  des goûts en excluant les films déjà notés. Réponse : `{"results": [{"qid", "label"}, ...]}`.
  `503` si les embeddings ne sont pas chargés.

Exemple `POST /recommend` :
```bash
curl -X POST http://127.0.0.1:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{
        "ratings": [
          {"qid": "Q172241", "rating": 9.0},
          {"qid": "Q44578",  "rating": 4.0}
        ],
        "mode": "mvp",
        "n": 10,
        "exclude": [],
        "explain": false
      }'
```

Exemple `GET /recommend` (notes du propriétaire) :
```bash
curl "http://127.0.0.1:8000/recommend?mode=hybrid&n=10"
```

Si un artefact requis manque, l'app démarre quand même et l'endpoint concerné répond
`503` avec un message clair (en français).

## Tests
```bash
pytest -q
```

## Développer avec Claude Code
Le dépôt est prêt pour Claude Code : `CLAUDE.md` fournit le contexte et les contraintes,
`.claude/rules/data-sources.md` verrouille la politique de licences, et `ROADMAP.md`
liste les tâches d'implémentation.

```bash
cd movie-reco
claude
```
Puis, par exemple : « Lis CLAUDE.md et ROADMAP.md, puis attaque la Phase 1 ».
Astuce : le mode plan et la réflexion étendue aident sur les étapes structurantes.

## Structure
```
movreco/
  ingest/      Wikidata (SPARQL), appariement, synopsis Wikipedia
  features/    structuré, embeddings, assemblage des features
  model/       vecteur de gout (MVP), preference (hybride), evaluation
  recommend/   index FAISS, diversite MMR, pipeline
  llm/         re-ranking et explications (optionnel)
  cli.py       interface en ligne de commande
config/        config.yaml
data/          input (ta liste), raw, processed
models/        index FAISS, modele de preference
tests/         tests des fonctions pures
```
