# Analyse du projet `movie-reco` (movreco)

> Recommandeur de films **personnel, mono-utilisateur, cold-start** — content-based + préférence
> supervisée, données libres (Wikidata CC0 + Wikipedia CC BY-SA), destiné à un usage commercial.
> Code analysé : ~1080 lignes Python, 7 commandes CLI, 4 fichiers de tests.

## Verdict global

Projet **propre, cohérent et bien architecturé** pour un squelette assumé (voir `ROADMAP.md`). Les
conventions du `CLAUDE.md` sont respectées (imports lourds paresseux, persistance Parquet/`.npy`/joblib,
`feature_matrix` unique pour entraînement **et** prédiction, messages CLI en français). La **conformité
des licences — la contrainte centrale du projet — est saine** : aucune source interdite n'est utilisée.

Cela dit, l'analyse a confirmé **1 bug critique latent**, **2 bugs élevés** et plusieurs défauts moyens
qui touchent directement la **correction des recommandations**, pas seulement la robustesse. À traiter
avant toute mise en production.

### Méthodologie
- Lecture intégrale du code, des tests, de la config et des docs.
- Exécution réelle de la suite de tests : **`10 passed`** (dépendances légères : numpy, pandas, rapidfuzz, pytest).
- Reproduction empirique des bugs ML clés (vecteur de goût nul, incohérence d'échelle de la pénalité).
- Analyse multi-agents (82 agents : 7 dimensions × revue + vérification adverse + passe de complétude).

---

## Points forts (à préserver)

- **Conformité des sources : conforme.** Les seuls accès réseau sont l'endpoint SPARQL Wikidata (CC0) et
  l'API REST Wikipedia (CC BY-SA). Aucune trace de MovieLens / datasets IMDb / Trakt / TMDB.
  L'identifiant IMDb récupéré (`P345`) vient de Wikidata (CC0) : c'est un **ID**, pas le dataset IMDb — bénin.
- **Pas de fuite de données dans l'apprentissage.** La popularité (sitelinks Wikidata) sert uniquement de
  **pénalité de classement**, jamais de feature d'entraînement → le modèle apprend bien le goût propre de
  l'utilisateur (exigence explicite du `CLAUDE.md`).
- **Exposition CC BY-SA limitée côté sortie.** Le CLI n'affiche que `qid`/`label`/`score`, jamais le texte
  Wikipedia.
- **Contrat d'alignement bien pensé et documenté**, `feature_matrix` partagée train/predict (garantit des
  colonnes identiques), normalisations gardées contre la division par zéro (`minmax`, `popularity_penalty`).
- **Tests = fonctions pures uniquement** (pas de réseau) : bonne pratique, et ils passent.
- Cohérence README / CLI / `config.yaml` correcte ; `user_agent` Wikidata bien présent.

---

## Constats confirmés, par sévérité

### 🔴 CRITIQUE

**C1 — Désalignement silencieux embeddings ↔ items (le garde-fou existe mais n'est jamais branché).**
`movreco/cli.py:149`, `movreco/features/combine.py:18`, `movreco/recommend/pipeline.py:37-66`
Le contrat suppose `emb[i] ↔ items["qid"][i]`. Or `embeddings.npy` est purement **positionnel** et
`items.parquet` est rechargé séparément. `embed()` écrit bien `embeddings_ids.json`… **mais ce fichier
n'est jamais relu** (vérifié : une seule occurrence dans tout le code, l'écriture).
Déclencheur réaliste : relancer `ingest` sans relancer `embed`. `fetch_catalog_by_year` utilise
`LIMIT` **sans `ORDER BY`** (`wikidata.py:111`), le contenu Wikidata évolue, puis
`drop_duplicates().reset_index(drop=True)` (`cli.py:86`) réattribue les positions. À taille égale, le
désalignement passe **sans aucune erreur** : vecteur de goût, retrieval FAISS, scoring hybride et top-N
deviennent faux tout en restant *plausibles* — le pire cas pour un produit.
**Correctif :** au chargement, relire `embeddings_ids.json` et vérifier l'égalité avec `items["qid"]`
(sinon erreur explicite « relance `movreco embed` après `ingest` »), ou mieux, **persister les embeddings
indexés par qid** plutôt qu'un `.npy` positionnel.

### 🟠 ÉLEVÉ

**E1 — Vecteur de goût nul quand toutes les notes sont égales (ou une seule note).** *(reproduit empiriquement)*
`movreco/model/taste_vector.py:13-17`
`weights = r - r.mean()` → si toutes les notes sont identiques, `weights = 0` → vecteur **nul** renvoyé
silencieusement. FAISS interroge alors avec une requête nulle (scores tous à 0 → ordre arbitraire) et,
en mode MVP, `cosine_scores` donne 0 partout (puis `minmax` écrase le signal). Cas **fréquent en
cold-start** (« j'ai mis 8 à tous mes films préférés »). Le pool de candidats étant pollué, **le mode
hybride est aussi affecté** (le modèle ne fait que reclasser une liste non personnalisée).
**Correctif :** détecter variance/vecteur nul, basculer sur un repli explicite (moyenne des embeddings
des films aimés au-dessus d'un **seuil absolu**) et avertir l'utilisateur que ses notes manquent de contraste.

**E2 — Le re-ranking LLM peut tronquer / dupliquer / perdre des recommandations, sans avertissement.**
`movreco/cli.py:243-253` (actif seulement si `llm.enabled: true`)
`result = result.iloc[idx]` où `idx` vient directement de la sortie LLM, sans garantir la **complétude**
ni l'**unicité**. Si le LLM renvoie 7 indices sur 20 → l'utilisateur reçoit 7 recos ; s'il duplique un
indice → films en double. La couche optionnelle devient un **filtre destructif** alors qu'elle ne doit
que réordonner/expliquer (cf. `llm/rerank.py:1-6`).
**Correctif :** dédupliquer en préservant l'ordre LLM, puis compléter avec les indices manquants dans
l'ordre du pipeline (permutation complète, longueur inchangée) ; aligner `expl` en conséquence.

### 🟡 MOYEN

**M1 — La pénalité de popularité est quasi inopérante en mode `hybrid` (le mode par défaut).** *(reproduit empiriquement)*
`movreco/recommend/pipeline.py:62-63` + `movreco/recommend/diversity.py:7-19`
`popularity_penalty` soustrait `weight·p` avec `p ∈ [0,1]` et `weight=0.15`, **directement** aux scores.
En MVP les scores sont des cosinus (~[-1,1]) : 0.15 **inverse le classement**. En hybride ce sont des
**notes prédites** (~0-10) : 0.15 est **négligeable** → le dé-biais « anti-blockbuster » ne fonctionne
pas dans le mode produit. Démonstration : `[6.0, 6.6]` avec pop `[1, 1e6]` → `[5.99, 6.45]` (le
blockbuster reste devant).
**Correctif :** appliquer la pénalité sur des scores **normalisés** (`minmax`) dans les deux modes, ou
calibrer `weight` selon l'échelle du mode.

**M2 — Sur-apprentissage garanti en cold-start ; aucun garde-fou de taille d'échantillon.**
`movreco/model/preference.py:18-27`, `movreco/cli.py:226-229`
LightGBM avec `num_boost_round=300`, `num_leaves=31` sur **~9 lignes** et des **centaines** de features
(embedding 384d + multihot genres/réal./pays/décennies) → mémorisation du bruit. Le repli MVP ne se
déclenche que si le **fichier** modèle est absent, jamais selon `n`.
**Correctif :** régularisation adaptée au petit `n` (`lambda_l1/l2`, `max_depth` faible,
`num_boost_round` fonction de `n` / early stopping), réduction de dimension, **seuil `n_min`** avant
d'autoriser le mode hybride, et comparaison systématique à la baseline MVP.

**M3 — Schéma des features structurées non figé.**
`movreco/features/structured.py:9-20`
Les colonnes (top-K labels) dépendent du **snapshot du catalogue** au moment de `features`. Réexécuter
`features` après un `ingest` différent change l'ensemble/l'ordre des colonnes → un modèle entraîné sur
l'ancien schéma devient incohérent (lié à C1).
**Correctif :** persister la liste des colonnes/vocabulaire et la réappliquer au scoring.

**M4 — `except Exception` masque les vraies erreurs LightGBM → repli sklearn silencieux.**
`movreco/model/preference.py:28-33`
Le `try` couvre tout le bloc (import **et** entraînement) : un bug d'usage de LightGBM bascule en silence
sur `GradientBoostingRegressor`, rendant les résultats non reproductibles et le diagnostic difficile.
**Correctif :** n'attraper que `ImportError` pour le repli ; logger explicitement le moteur retenu.

**M5 — `match_ratings` (le code le plus sujet aux bugs) n'est pas testé.**
`movreco/ingest/matching.py:31-68`
Seuil `fuzzy_threshold=86` + bonus année `+10` : un mauvais titre peut passer le seuil grâce au bonus
année. Aucun test ne couvre cette logique (seul `normalize_title` l'est).
**Correctif :** tests sur le scoring/seuil/bonus avec candidats simulés ; envisager une désambiguïsation
par année plus stricte.

### 🟢 BAS (robustesse, UX, dette)

- **B1 — `lookup_film` interpole le titre en ne neutralisant que les guillemets** (`wikidata.py:67-86`).
  Sauts de ligne/backslash peuvent **casser** la requête. Risque d'injection réel faible (paramètre de
  recherche, endpoint public en lecture seule) mais à durcir (échappement/validation).
- **B2 — CSV `rating` non validé** (`cli.py:65,181,276`) : une valeur non numérique lève un `ValueError`
  brut au lieu d'un message FR. Le pattern correctif existe déjà ailleurs (`pd.to_numeric(..., errors="coerce")`, `cli.py:44`).
- **B3 — `loo_mae` renvoie `NaN` silencieusement si `n<3`** (`evaluate.py:31`) — à signaler à l'utilisateur.
- **B4 — Catalogue tronqué par `LIMIT` sans `ORDER BY`** (`wikidata.py:111`) : sous-ensemble arbitraire et
  non reproductible pour les années > 1500 films. Ajouter `ORDER BY DESC(?popularity)`.
- **B5 — Texte brut Wikipedia persistant** dans `data/raw/synopsis.parquet` (`cli.py:119-123`). Conforme à
  la *lettre* (gitignoré, usage local pour embeddings) mais le `CLAUDE.md` recommande de stocker des
  embeddings plutôt que le texte. Durcissement : encoder en flux ou purger après `embed` (risque de fuite
  via image/backup).
- **B6 — Code mort / non câblé** : `save_index`/`load_index` + chemin `P["faiss"]` jamais utilisés (FAISS
  reconstruit à chaque `recommend`) ; `ndcg_at_k` testé mais jamais branché en CLI. (ROADMAP en a conscience.)
- **B7 — `fetch_summary`** : pas de retry/backoff, avale les erreurs en `None` (ne distingue pas « absent »
  de « échec réseau »), User-Agent codé en dur `movreco/0.1` (`synopsis.py:14-27`).
- **B8 — `run_sparql` ignore l'en-tête `Retry-After`** sur 429 (`wikidata.py:53`).
- **B9 — `paths(cfg)` ignore son paramètre `cfg`** (`config.py:29-40`) : chemins codés en dur, aucune
  relocalisation possible (gênant pour déploiement/tests). Lire `data_dir`/`models_dir`, ou retirer le param.
- **B10 — `DBpedia` documenté partout** (README/CLAUDE/DATA_LICENSES) **mais jamais utilisé** (seule l'API
  REST Wikipedia l'est). Aligner la doc.
- **B11 — Packaging** : `anthropic` (couche LLM **optionnelle**) est une dépendance **obligatoire** dans
  `pyproject.toml` → devrait être un extra `[llm]`. `requirements.txt` **duplique** `pyproject` (risque de
  dérive). Pas de fichier `LICENSE` ni de clé `license` (important pour un produit commercial).
  `user_agent` reste un placeholder `example.org` à remplacer.

### Couverture de tests — lacunes prioritaires
Non testés : `feature_matrix` (alignement / qid manquants), `build_structured_features`, `match_ratings`,
`loo_mae`, `_normalize_catalog`, le **pipeline `recommend` de bout en bout**, et les **cas dégénérés**
(notes toutes égales → E1, catalogue vide, `minmax` constant). Quelques assertions sont faibles
(ex. `test_ndcg_reverse_order` n'assert que `< 1.0`).

---

## Plan d'action recommandé

1. **C1** — brancher la vérification `embeddings_ids.json` (ou indexer les embeddings par qid). *Bloquant produit.*
2. **E1 / E2** — repli explicite pour le vecteur de goût nul ; rendre le re-rank LLM non destructif.
3. **M1 / M4** — normaliser les scores avant la pénalité de popularité ; restreindre le `except` au seul `ImportError`.
4. **M2 / M5** — garde-fou `n_min` + régularisation cold-start ; tests sur `match_ratings`.
5. **Quick wins** : validation du CSV (B2), `ORDER BY` catalogue (B4), `anthropic` en extra + `LICENSE` (B11),
   purge/streaming du texte Wikipedia (B5), aligner la doc DBpedia (B10).

*Les références `fichier:ligne` portent sur l'arborescence `movie-reco/` du zip fourni.*
