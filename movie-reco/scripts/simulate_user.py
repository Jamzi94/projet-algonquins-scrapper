#!/usr/bin/env python3
"""Simulation d'un PARCOURS UTILISATEUR de bout en bout sur l'API movreco.

Construit un catalogue synthétique (groupé par genre, aucun réseau, aucun
sentence-transformers), monte l'application FastAPI via TestClient, puis joue un
scénario narré en français :

  1. L'utilisateur vérifie que le service est en ligne      (GET /health)
  2. Il recherche des films                                 (GET /movies?q=)
  3. Il note plusieurs films d'un genre précis              (POST /recommend)
  4. On affiche le top-N reçu
  5. Il demande des films similaires à l'un d'eux           (GET /movies/{qid}/similar)

À la fin, on calcule un score de pertinence (part du top-N partageant le genre
aimé) et on imprime "VALIDATION: PASS" si >= 0.6, sinon "VALIDATION: FAIL", avec
un code de sortie 0/1 correspondant. Exécutable directement :

    python scripts/simulate_user.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Permet l'exécution directe (python scripts/simulate_user.py) sans installation :
# on ajoute la racine du dépôt au sys.path pour importer `movreco` et `tests`.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SEUIL_PERTINENCE = 0.6
GENRE_AIME = "Genre 2"


def _section(titre: str) -> None:
    print()
    print("=" * 70)
    print(titre)
    print("=" * 70)


def main() -> int:
    from fastapi.testclient import TestClient

    from movreco.api.app import create_app
    from tests._synthetic import build_synthetic_catalog

    print("Simulation d'un utilisateur réel sur le moteur de recommandation movreco")
    print("(catalogue synthétique, hors ligne, sans sentence-transformers)")

    with tempfile.TemporaryDirectory() as tmp:
        ctx = build_synthetic_catalog(Path(tmp), n_genres=4, per_genre=15, dim=16, seed=0)
        qid_to_genre = ctx["qid_to_genre"]

        app = create_app(ctx["cfg"])
        with TestClient(app) as client:

            # --- 1. Santé du service -------------------------------------- #
            _section("1. L'utilisateur vérifie que le service est disponible")
            health = client.get("/health").json()
            arts = health["artifacts"]
            print(f"Statut du service : {health['status']}")
            print(f"  Films au catalogue : {arts['items']}")
            print(f"  Embeddings chargés : {'oui' if arts['embeddings'] else 'non'}")
            print(f"  Features structurées : {'oui' if arts['structured'] else 'non'}")
            print(f"  Modèle de préférence : {'oui' if arts['model'] else 'non'}")
            print(f"  Notes du propriétaire : {arts['rated']}")

            # --- 2. Recherche de films ------------------------------------ #
            _section(f"2. L'utilisateur recherche des films du « {GENRE_AIME} »")
            recherche = client.get(
                "/movies", params={"q": GENRE_AIME, "limit": 5}
            ).json()["results"]
            print(f"{len(recherche)} résultat(s) affiché(s) (5 premiers) :")
            for film in recherche:
                annee = film["year"] if film["year"] is not None else "?"
                print(f"  - {film['qid']} | {film['label']} ({annee}) | {film['genres']}")

            # --- 3. L'utilisateur note plusieurs films du genre aimé ------ #
            _section(f"3. L'utilisateur note 3 films du « {GENRE_AIME} » (5/5)")
            notes = ctx["genre_to_qids"][GENRE_AIME][:3]
            for qid in notes:
                detail = client.get(f"/movies/{qid}").json()
                print(f"  Note 5/5 -> {qid} | {detail['label']}")

            payload = {
                "ratings": [{"qid": qid, "rating": 5.0} for qid in notes],
                "mode": "mvp",
                "n": 10,
            }
            reco = client.post("/recommend", json=payload)
            if reco.status_code != 200:
                print(f"ERREUR : POST /recommend a renvoyé {reco.status_code}")
                print("VALIDATION: FAIL")
                return 1
            reco = reco.json()

            # --- 4. Affichage du top-N reçu ------------------------------- #
            _section("4. Recommandations reçues (top-N)")
            print(f"Mode de scoring effectif : {reco['mode']}")
            resultats = reco["results"]
            for rang, film in enumerate(resultats, start=1):
                genre = qid_to_genre.get(film["qid"], "?")
                marque = "<-- genre aimé" if genre == GENRE_AIME else ""
                print(
                    f"  {rang:>2}. {film['qid']} | {film['label']} "
                    f"| score={film['score']:.3f} | {genre} {marque}"
                )

            # --- 5. Films similaires -------------------------------------- #
            _section("5. L'utilisateur demande des films similaires au 1er recommandé")
            cible = resultats[0]["qid"]
            sim = client.get(f"/movies/{cible}/similar", params={"n": 5}).json()
            print(f"Film de référence : {sim['query']['qid']} | {sim['query']['label']}")
            for film in sim["results"]:
                genre = qid_to_genre.get(film["qid"], "?")
                print(
                    f"  - {film['qid']} | {film['label']} "
                    f"| similarité={film['score']:.3f} | {genre}"
                )

            # --- Validation de pertinence --------------------------------- #
            _section("BILAN — Validation de la pertinence")
            if resultats:
                part = sum(
                    1 for f in resultats if qid_to_genre.get(f["qid"]) == GENRE_AIME
                ) / len(resultats)
            else:
                part = 0.0
            print(
                f"Part du top-N partageant le genre aimé « {GENRE_AIME} » : "
                f"{part:.0%} (seuil = {SEUIL_PERTINENCE:.0%})"
            )

            if part >= SEUIL_PERTINENCE:
                print("VALIDATION: PASS")
                return 0
            print("VALIDATION: FAIL")
            return 1


if __name__ == "__main__":
    sys.exit(main())
