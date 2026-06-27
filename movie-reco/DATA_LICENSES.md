# Licences des données

Ce projet vise un usage commercial. Synthèse des obligations.

## Sources utilisées dans le produit

### Wikidata — CC0 1.0
Domaine public. Aucune restriction, redistribution libre y compris commerciale.
Aucune obligation d'attribution (mais la citer reste courtois).

### Wikipedia / DBpedia — CC BY-SA
Usage commercial autorisé, sous deux conditions :
- **Attribution** : créditer Wikipedia et les auteurs.
- **Partage à l'identique** : toute oeuvre dérivée du texte doit être publiée sous la même licence.

Recommandation : stocker et exposer des **embeddings** (vecteurs) plutôt que republier le
texte brut. Les vecteurs dérivés sont une zone moins exposée que la republication intégrale.
Si tu exposes des extraits, ajoute l'attribution et la mention de licence.

## Sources EXCLUES du produit
À ne pas intégrer au livrable commercial (utilisables seulement en local/privé pour test) :
- **MovieLens / GroupLens** : usage commercial interdit sans autorisation préalable du laboratoire.
- **Datasets IMDb** : usage non commercial uniquement.
- **API Trakt** : usage personnel ; le commercial qui monétise ou génère du trafic significatif exige une approbation.
- **TMDB** : usage commercial soumis à un accord spécial.

## Code (bibliothèques)
LightGBM, scikit-learn, sentence-transformers, FAISS, pandas, numpy, typer, rapidfuzz : licences
permissives (MIT/Apache/BSD), compatibles commercial. Vérifier la licence du **modèle d'embedding**
précis téléchargé depuis Hugging Face (souvent Apache-2.0, à confirmer pour le modèle retenu).
