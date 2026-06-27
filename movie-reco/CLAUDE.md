# movreco — contexte projet pour Claude Code

Recommandeur de films **personnel** (un seul utilisateur, sa liste de films notés en entrée).
Projet destiné à devenir **public/commercial** : la conformité des licences de données est non négociable.

## Architecture en un coup d'oeil
Pipeline en étapes, orchestré par une CLI Typer (`movreco/cli.py`) :
`ingest` (Wikidata) -> `synopsis` (Wikipedia) -> `embed` (sentence-transformers) -> `features` (structuré) -> `train` (LightGBM) -> `recommend`.
- `movreco/ingest/` : récupération et appariement des données (SPARQL Wikidata, REST Wikipedia).
- `movreco/features/` : features structurées + embeddings + assemblage (`combine.feature_matrix`).
- `movreco/model/` : vecteur de goût (MVP), modèle de préférence supervisé (hybride), évaluation.
- `movreco/recommend/` : index FAISS, diversité MMR, pipeline.
- `movreco/llm/` : couche LLM optionnelle (re-ranking/explication), désactivée par défaut.

Cas technique : **mono-utilisateur en cold-start**. Le coeur est *content-based + apprentissage de préférence supervisé*, PAS du filtrage collaboratif.

## Contraintes de données (CRITIQUE)
**YOU MUST** n'utiliser que des sources libres pour usage commercial :
- Métadonnées : **Wikidata uniquement** (CC0).
- Texte/synopsis : **Wikipedia/DBpedia** (CC BY-SA, attribution + partage à l'identique).

**NEVER** introduire dans le produit : MovieLens, datasets IMDb, API Trakt, ni TMDB. Tous imposent des restrictions commerciales ou une autorisation. Voir `DATA_LICENSES.md`.
**IMPORTANT** : stocker des **embeddings** plutôt que republier le texte brut Wikipedia (limite l'exposition CC BY-SA).

## Conventions de code
- Python >= 3.11, type hints, `from __future__ import annotations`.
- Imports lourds (`sentence_transformers`, `faiss`, `lightgbm`, `anthropic`) importés **dans les fonctions**, jamais au niveau module, pour garder la CLI rapide.
- Persistance : Parquet pour les tables, `.npy` pour les embeddings, FAISS/joblib pour index et modèle. Chemins centralisés dans `movreco/config.py:paths()`.
- Contrat d'alignement : `items` (DataFrame), `emb` (numpy aligné sur les lignes de `items`), `structured` (DataFrame indexé par qid). Toujours passer par `features.combine.feature_matrix` pour entraînement ET prédiction.
- Français pour les messages CLI et la doc.

## Commandes
- Install : `pip install -e ".[dev]"`
- Tests : `pytest -q`
- Pipeline : voir `README.md` et la liste de tâches dans `ROADMAP.md`.

## Pièges connus
- Wikidata exige un User-Agent (config.yaml). Requêtes par année pour éviter les timeouts.
- Appariement titre/année imparfait (homonymes, titres localisés). Le rapport `data/processed/matching_report.csv` doit être vérifié à la main.
- Éviter toute fuite de données : ne pas mettre une note moyenne externe dans les features (on veut le goût propre de l'utilisateur).

La liste de tâches d'implémentation est dans `ROADMAP.md` (ne pas la dupliquer ici).
