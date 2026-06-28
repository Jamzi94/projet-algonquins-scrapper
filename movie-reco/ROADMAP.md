# Feuille de route d'implémentation

Cible : système hybride, construit en deux temps. Le MVP embeddings (Phase 1) est
la couche de retrieval du système hybride : rien n'est jeté.

Statut du squelette : le pipeline complet est posé et importable. Les étapes
ci-dessous consistent à fiabiliser, tester sur données réelles, et raffiner.

Correctifs déjà appliqués : garde-fou d'alignement des embeddings (`emb_ids`),
normalisation de la popularité, re-rank LLM fiabilisé, validation du CSV de notes.

## Phase 0 — Préparation
- [ ] Copier `data/input/ratings.example.csv` en `data/input/ratings.csv` et y mettre ta vraie liste (colonnes : title, year, rating).
- [ ] Choisir l'échelle de notes et la garder cohérente (ex. 0-10 avec décimales, ou 0-100).
- [ ] `pip install -e ".[dev]"` puis `pytest -q` (les tests des fonctions pures doivent passer).

## Phase 1 — MVP embeddings (retrieval)
- [ ] `movreco ingest` : vérifier le taux d'appariement, corriger `matching_report.csv` à la main si besoin.
- [ ] Améliorer `ingest/matching.py` : gérer titres localisés (P1476/altLabels), seuil adaptatif, désambiguïsation par année stricte.
- [x] `movreco synopsis` : passer du résumé (lead) au texte complet via l'API `action=query&prop=extracts&explaintext` pour des embeddings plus riches.
- [ ] `movreco embed` puis `movreco recommend --mode mvp` : revue qualitative du top-N.
- [ ] Régler `recommend.candidates`, `mmr_lambda`, `popularity_penalty` dans `config.yaml`.

## Phase 2 — Couche hybride (préférence supervisée)
- [x] `movreco features` : enrichir les features structurées (acteurs P161, mots-clés, durée, langue).
- [ ] `movreco train` : viser une MAE leave-one-out raisonnable ; itérer sur les features.
- [ ] `movreco recommend --mode hybrid` : comparer au mode mvp sur ta revue qualitative.
- [x] Ajouter une vraie évaluation de classement (NDCG@k sur split temporel) dans `model/evaluate.py`.

## Phase 3 — Robustesse et produit
- [x] Mettre en cache les appels Wikidata/Wikipedia (éviter de refaire les requêtes).
- [x] Persister l'index FAISS (`save_index`/`load_index`) au lieu de le reconstruire à chaque reco.
- [x] Boucle d'apprentissage actif : proposer en priorité des films à fort gain d'information.
- [x] Sérendipité contrôlée : réserver une fraction du top-N à des items pertinents mais éloignés.
- [x] Exposer une petite API (FastAPI) ou une UI si besoin produit.

## Phase 4 — Option LLM
- [ ] Activer `llm.enabled` dans `config.yaml`, renseigner `ANTHROPIC_API_KEY` dans `.env`.
- [ ] Fiabiliser le mapping index/explication dans `cli.recommend` après re-ranking LLM.

## Conformité (permanent)
- [ ] Vérifier qu'aucune source interdite n'est entrée dans le produit (voir `.claude/rules/data-sources.md`).
- [ ] Préparer l'attribution CC BY-SA si du texte Wikipedia est exposé.
