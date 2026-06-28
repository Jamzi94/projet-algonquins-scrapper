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
  6. Apprentissage actif : des films à noter en priorité    (GET /suggest)
  7. Sérendipité : un top-N qui ose sortir du genre dominant (pipeline.recommend)

À la fin, on agrège plusieurs vérifications (pertinence du top-N, couverture de
l'apprentissage actif, effet de la sérendipité) et on imprime "VALIDATION: PASS"
si TOUTES sont satisfaites, sinon "VALIDATION: FAIL", avec un code de sortie 0/1
correspondant. Exécutable directement :

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
        # Catalogue ENRICHI (cast/keywords/langues/durée) pour exercer aussi les
        # features étendues ; le reste du parcours est inchangé.
        ctx = build_synthetic_catalog(
            Path(tmp), n_genres=4, per_genre=15, dim=16, seed=0, enriched=True
        )
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

            # --- 6. Apprentissage actif ----------------------------------- #
            _section("6. Apprentissage actif : quels films noter en priorité ?")
            print(
                "Le moteur propose des films COUVRANT l'espace des goûts (films "
                "éloignés de ce qui est déjà connu), pas des doublons."
            )
            sugg_resp = client.get("/suggest", params={"n": 8})
            suggestions = (
                sugg_resp.json()["results"] if sugg_resp.status_code == 200 else []
            )
            owner_qids = set(ctx["owner_qids"])
            genres_couverts: set[str] = set()
            for rang, film in enumerate(suggestions, start=1):
                genre = qid_to_genre.get(film["qid"], "?")
                genres_couverts.add(genre)
                print(f"  {rang:>2}. {film['qid']} | {film['label']} | {genre}")
            # Sous-verdict actif : suggestions non notées ET couvrant >= 2 genres.
            actif_exclut_notes = all(f["qid"] not in owner_qids for f in suggestions)
            actif_couvre = len(genres_couverts) >= 2
            print(
                f"Genres couverts par les suggestions : {len(genres_couverts)} "
                f"({', '.join(sorted(genres_couverts)) or 'aucun'})"
            )
            ok_actif = bool(suggestions) and actif_exclut_notes and actif_couvre

            # --- 7. Sérendipité ------------------------------------------- #
            _section("7. Sérendipité : un top-N qui ose sortir du genre dominant")
            print(
                "On compare, sur les MÊMES notes, un top-N sans sérendipité (0.0) "
                "à un top-N avec sérendipité (>0) : ce dernier doit faire émerger "
                "au moins un film hors du genre aimé."
            )
            ok_serendipite = False
            try:
                import numpy as np

                from movreco.recommend.pipeline import recommend as run_reco

                liked_ser = ctx["genre_to_qids"][GENRE_AIME][:3]
                ratings_ser = np.array([5.0] * len(liked_ser), dtype=float)

                def _reco_serendipite(valeur: float):
                    cfg = dict(ctx["cfg"])
                    rc = dict(cfg.get("recommend", {}) or {})
                    rc["top_n"] = 10
                    rc["serendipity"] = valeur
                    cfg["recommend"] = rc
                    return run_reco(
                        ctx["items"], ctx["emb"], liked_ser, ratings_ser,
                        mode="mvp", cfg=cfg,
                    )

                base = _reco_serendipite(0.0)
                ser = _reco_serendipite(0.4)
                base_off = sum(
                    1 for q in base["qid"] if qid_to_genre.get(q) != GENRE_AIME
                )
                ser_off = [q for q in ser["qid"] if qid_to_genre.get(q) != GENRE_AIME]
                print(f"  Sans sérendipité (0.0) : {base_off} film(s) hors-genre.")
                print(
                    f"  Avec sérendipité (0.4) : {len(ser_off)} film(s) hors-genre."
                )
                for q in ser_off:
                    label = ctx["items"].set_index("qid").loc[q, "label"]
                    print(f"     -> {q} | {label} | {qid_to_genre.get(q)}")
                # Sous-verdict : la sérendipité introduit au moins un hors-genre,
                # plus que sans, et conserve une longueur de top-N de 10 sans doublon.
                ok_serendipite = (
                    len(ser) == 10
                    and len(set(ser["qid"])) == 10
                    and len(ser_off) >= 1
                    and len(ser_off) > base_off
                )
            except Exception as exc:  # pragma: no cover - robustesse de la démo
                print(f"  (Sérendipité indisponible : {exc})")

            # --- BILAN agrégé --------------------------------------------- #
            _section("BILAN — Validation globale du parcours")
            if resultats:
                part = sum(
                    1 for f in resultats if qid_to_genre.get(f["qid"]) == GENRE_AIME
                ) / len(resultats)
            else:
                part = 0.0
            ok_pertinence = part >= SEUIL_PERTINENCE

            print(
                f"  Pertinence du top-N (genre « {GENRE_AIME} ») : "
                f"{part:.0%} >= {SEUIL_PERTINENCE:.0%} ? "
                f"{'OUI' if ok_pertinence else 'NON'}"
            )
            print(
                "  Apprentissage actif (suggestions non notées, >= 2 genres) : "
                f"{'OUI' if ok_actif else 'NON'}"
            )
            print(
                "  Sérendipité (>= 1 film hors-genre vs base) : "
                f"{'OUI' if ok_serendipite else 'NON'}"
            )

            if ok_pertinence and ok_actif and ok_serendipite:
                print("VALIDATION: PASS")
                return 0
            print("VALIDATION: FAIL")
            return 1


if __name__ == "__main__":
    sys.exit(main())
