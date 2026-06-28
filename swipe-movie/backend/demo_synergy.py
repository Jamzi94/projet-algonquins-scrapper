#!/usr/bin/env python3
"""Démonstration narrée de la SYNERGIE SwipeNight x movie-reco (hors-ligne).

Ce script EXÉCUTABLE raconte, en français, le scénario d'intégration de bout en
bout, SANS réseau ni modèle lourd :

  1. construit un petit catalogue synthétique groupé par genre (le helper de tests
     de movie-reco écrit items/embeddings/structured/rated sur disque) ;
  2. charge le pont :class:`recommender_bridge.SynergyEngine` (catalogue + scoring
     proviennent de movreco — Wikidata CC0 / Wikipedia CC BY-SA — sans TMDB) ;
  3. simule un utilisateur qui swipe « like » sur des films de science-fiction et
     affiche ses recommandations ;
  4. crée une room de 2 utilisateurs aux goûts différents et affiche le choix de
     groupe agrégé par ``recommender.group_score`` (apport propre de SwipeNight) ;
  5. affiche les titres de calibration proposés à la notation (apprentissage actif).

À la fin, il calcule un score de PERTINENCE (part du top-N qui partage le genre
aimé) et imprime « VALIDATION: PASS » avec un code de sortie 0 si ce score est
>= 60 %, sinon « VALIDATION: FAIL » avec un code de sortie 1.

Usage :
    python demo_synergy.py
"""
from __future__ import annotations

import sys
import tempfile
from collections import Counter
from pathlib import Path

# --------------------------------------------------------------------------- #
# Chemins : ce script vit dans swipe-movie/backend/. On ajoute :
#   - backend           -> pour importer recommender_bridge / recommender ;
#   - racine du dépôt   -> pour atteindre movie-reco (frère) ;
#   - movie-reco        -> pour importer le paquet movreco (non pip-installé) ;
#   - movie-reco/tests  -> pour réutiliser _synthetic.build_synthetic_catalog.
# movreco n'importe les libs lourdes que dans embed : ces imports restent légers.
# --------------------------------------------------------------------------- #
_BACKEND = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND.parents[1]
_MOVRECO_ROOT = _REPO_ROOT / "movie-reco"
for _p in (str(_BACKEND), str(_MOVRECO_ROOT), str(_MOVRECO_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# Seuil de pertinence minimal pour valider la synergie (part du top-N même genre).
SEUIL_PERTINENCE = 0.60
TOP_N = 10


def _titre(texte: str) -> None:
    """Affiche un titre de section encadré."""
    barre = "=" * 70
    print(f"\n{barre}\n{texte}\n{barre}")


def main() -> int:
    from _synthetic import build_synthetic_catalog

    import recommender_bridge as RB

    _titre("SYNERGIE SwipeNight x movie-reco — démonstration hors-ligne")
    print(
        "Catalogue + scoring fournis par movreco (Wikidata CC0 + Wikipedia CC "
        "BY-SA).\nAucune source TMDB, aucun accès réseau, aucun modèle lourd.\n"
        "Les rooms multi-utilisateurs réutilisent recommender.group_score "
        "(SwipeNight)."
    )

    # ------------------------------------------------------------------- #
    # 1) Catalogue synthétique groupé par genre (déterministe).
    # ------------------------------------------------------------------- #
    tmp_dir = tempfile.mkdtemp(prefix="demo_synergy_")
    data = build_synthetic_catalog(
        tmp_dir, n_genres=4, per_genre=15, dim=16, seed=0
    )
    genre_to_qids = data["genre_to_qids"]
    qid_to_genre = data["qid_to_genre"]
    noms_genres = data["genre_names"]

    # On nomme le genre 0 « la science-fiction » pour la narration.
    genre_sf = noms_genres[0]
    genre_autre = noms_genres[2]

    _titre("1) Chargement du pont SynergyEngine")
    engine = RB.SynergyEngine.load(data["cfg"])
    statut = engine.provider_status()
    print(f"Source       : {statut['source']}")
    print(f"TMDB activé  : {statut['tmdb_enabled']}")
    print(f"Licence      : {statut['license']}")
    print(f"Taille cat.  : {statut['catalog_size']} films")
    apercu = engine.catalog(limit=3)
    print("Aperçu catalogue :")
    for c in apercu:
        print(f"  - {c['id']} | {c['title']} | genres={c['genres']}")

    # ------------------------------------------------------------------- #
    # 3) Utilisateur qui swipe « like » sur de la science-fiction.
    # ------------------------------------------------------------------- #
    _titre(f"2) Un utilisateur aime 3 films « {genre_sf} » (science-fiction)")
    aimes = genre_to_qids[genre_sf][:3]
    swipes = [{"qid": q, "action": "like"} for q in aimes]
    for q in aimes:
        print(f"  like  -> {q} ({qid_to_genre[q]})")

    recos = engine.recommend_for_user(swipes, n=TOP_N)
    print(f"\nRecommandations ({len(recos)}) :")
    for r in recos:
        print(
            f"  {r['score']:.3f}  {r['id']}  {r['title']:<22}"
            f"  [{qid_to_genre[r['id']]}]"
        )
        print(f"          raison: {r['reasons'][0]}")

    # Pertinence : part du top-N qui partage le genre aimé.
    genres_recos = Counter(qid_to_genre[r["id"]] for r in recos)
    same = genres_recos[genre_sf]
    pertinence = (same / len(recos)) if recos else 0.0
    print(
        f"\nPertinence : {same}/{len(recos)} = {pertinence:.0%} du top-N "
        f"partagent le genre « {genre_sf} »."
    )

    # ------------------------------------------------------------------- #
    # 4) Room de 2 utilisateurs aux goûts différents -> choix de groupe.
    # ------------------------------------------------------------------- #
    _titre("3) Une room de 2 utilisateurs aux goûts différents")
    membre_a = {
        "user": "Alice",
        "swipes": [{"qid": q, "action": "superlike"} for q in genre_to_qids[genre_sf][:3]],
    }
    membre_b = {
        "user": "Bob",
        "swipes": [{"qid": q, "action": "superlike"} for q in genre_to_qids[genre_autre][:3]],
    }
    print(f"  Alice adore « {genre_sf} », Bob adore « {genre_autre} ».")
    picks = engine.recommend_for_room([membre_a, membre_b], n=5)
    print(f"\nChoix de groupe ({len(picks)}) — agrégés par group_score :")
    for p in picks:
        comp = p["components"]
        print(
            f"  gs={p['group_score']:.3f}  {p['id']}  {p['title']:<22}"
            f"  [{qid_to_genre[p['id']]}]"
        )
        print(
            f"          moyenne={comp['mean_score']}  min={comp['min_score']}"
            f"  désaccord={comp['disagreement']}"
        )

    # ------------------------------------------------------------------- #
    # 5) Titres de calibration (apprentissage actif).
    # ------------------------------------------------------------------- #
    _titre("4) Titres de calibration (onboarding, apprentissage actif)")
    calibration = engine.calibration_titles(n=8)
    for t in calibration:
        print(f"  {t['id']}  {t['title']}  [{qid_to_genre[t['id']]}]")

    # ------------------------------------------------------------------- #
    # Verdict
    # ------------------------------------------------------------------- #
    _titre("VERDICT")
    if pertinence >= SEUIL_PERTINENCE:
        print(
            f"VALIDATION: PASS  ({pertinence:.0%} >= {SEUIL_PERTINENCE:.0%}) — "
            "la synergie ramène des films pertinents."
        )
        return 0
    print(
        f"VALIDATION: FAIL  ({pertinence:.0%} < {SEUIL_PERTINENCE:.0%}) — "
        "pertinence insuffisante."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
