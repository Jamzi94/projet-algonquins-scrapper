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
movreco evaluate               # MAE leave-one-out + NDCG@k (split temporel)
```
Artefacts dans `data/processed/` et `models/`. Vérifie `data/processed/matching_report.csv`
après l'ingestion (l'appariement titre/année est imparfait).

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
