"""Tests de la SÉRENDIPITÉ (Équipe 3) : helpers de diversité + pipeline.recommend.

On valide d'abord les helpers purs (``novelty_scores``, ``serendipity_picks``),
puis le comportement de bout en bout via ``pipeline.recommend`` sur un catalogue
synthétique multi-genres (nécessite faiss) :

  - serendipity=0.0 (défaut) -> recommandations STRICTEMENT inchangées ;
  - serendipity>0   -> au moins un item HORS du genre dominant apparaît, tout en
    conservant une longueur de top_n et sans doublon.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from movreco.recommend.diversity import novelty_scores, serendipity_picks


# --------------------------------------------------------------------------- #
# Helpers purs (pas de faiss requis)
# --------------------------------------------------------------------------- #
def test_novelty_scores_un_moins_cosinus():
    taste = np.array([1.0, 0.0])
    sub = np.array(
        [
            [1.0, 0.0],   # identique au goût -> cos 1 -> nouveauté 0
            [0.0, 1.0],   # orthogonal -> cos 0 -> nouveauté 1
            [-1.0, 0.0],  # opposé -> cos -1 -> nouveauté 2
        ]
    )
    nov = novelty_scores(sub, taste)
    assert nov.shape == (3,)
    assert nov[0] == pytest.approx(0.0, abs=1e-6)
    assert nov[1] == pytest.approx(1.0, abs=1e-6)
    assert nov[2] == pytest.approx(2.0, abs=1e-6)


def test_novelty_scores_vecteur_nul_robuste():
    taste = np.array([1.0, 0.0])
    sub = np.array([[0.0, 0.0]])  # norme nulle -> cos 0 -> nouveauté 1
    nov = novelty_scores(sub, taste)
    assert nov[0] == pytest.approx(1.0, abs=1e-6)


def test_novelty_scores_sub_emb_vide():
    nov = novelty_scores(np.zeros((0, 3)), np.array([1.0, 0.0, 0.0]))
    assert nov.shape == (0,)


def test_serendipity_picks_choisit_pertinent_mais_nouveau():
    cand_idx = [10, 11, 12, 13]
    # Pertinences au-dessus/en dessous de la médiane.
    relevance = np.array([0.9, 0.8, 0.1, 0.85])
    # Nouveautés : l'index 3 est le plus nouveau parmi les pertinents.
    novelty = np.array([0.1, 0.2, 5.0, 0.9])
    chosen_global, chosen_local = serendipity_picks(
        cand_idx, relevance, novelty, n_pick=1
    )
    assert len(chosen_global) == 1
    # cand 12 a une forte nouveauté MAIS une pertinence sous la médiane -> exclu.
    # Parmi les pertinents, le plus nouveau est le local 3 (global 13).
    assert chosen_local == [3]
    assert chosen_global == [13]


def test_serendipity_picks_exclut_already_local():
    cand_idx = [0, 1, 2, 3]
    relevance = np.array([0.9, 0.9, 0.9, 0.9])
    novelty = np.array([0.1, 0.5, 0.9, 0.2])
    # On exclut le plus nouveau (local 2) -> doit choisir le suivant (local 1).
    chosen_global, chosen_local = serendipity_picks(
        cand_idx, relevance, novelty, n_pick=1, already_local=[2]
    )
    assert chosen_local == [1]


def test_serendipity_picks_n_pick_nul():
    assert serendipity_picks([0, 1], np.array([1.0, 1.0]), np.array([1.0, 1.0]), 0) == (
        [],
        [],
    )


# --------------------------------------------------------------------------- #
# Bout en bout via pipeline.recommend (faiss requis)
# --------------------------------------------------------------------------- #
pytest.importorskip("faiss")

from tests._synthetic import build_synthetic_catalog  # noqa: E402


N_GENRES = 4
PER_GENRE = 15


@pytest.fixture()
def ctx():
    with tempfile.TemporaryDirectory() as tmp:
        yield build_synthetic_catalog(
            Path(tmp), n_genres=N_GENRES, per_genre=PER_GENRE, dim=16, seed=0
        )


def _recommend(ctx, serendipity: float, top_n: int = 10):
    from movreco.recommend.pipeline import recommend

    cfg = dict(ctx["cfg"])
    rc = dict(cfg.get("recommend", {}) or {})
    rc["top_n"] = top_n
    rc["serendipity"] = serendipity
    cfg["recommend"] = rc

    owner = ctx["owner_genre"]
    liked = ctx["genre_to_qids"][owner][:3]
    ratings = np.array([5.0] * len(liked), dtype=float)
    return recommend(
        ctx["items"], ctx["emb"], liked, ratings, mode="mvp", cfg=cfg
    )


def test_serendipity_absente_equivaut_a_zero(ctx):
    """Clé serendipity ABSENTE (défaut pipeline 0.0) == serendipity=0.0 explicite.

    Le contrat impose qu'en l'absence de réglage, le défaut soit 0.0 et ne change
    RIEN. On retire donc explicitement la clé (la config par défaut l'inclut à 0.2)
    pour vérifier que le repli interne du pipeline vaut bien 0.0.
    """
    from movreco.recommend.pipeline import recommend

    cfg = dict(ctx["cfg"])
    rc = dict(cfg.get("recommend", {}) or {})
    rc["top_n"] = 10
    rc.pop("serendipity", None)  # aucune clé -> défaut interne du pipeline
    cfg["recommend"] = rc

    owner = ctx["owner_genre"]
    liked = ctx["genre_to_qids"][owner][:3]
    ratings = np.array([5.0] * len(liked), dtype=float)
    sans_cle = recommend(ctx["items"], ctx["emb"], liked, ratings, mode="mvp", cfg=cfg)

    avec_zero = _recommend(ctx, serendipity=0.0, top_n=10)

    # Même longueur, mêmes qids dans le même ordre : défaut neutre confirmé.
    assert list(avec_zero["qid"]) == list(sans_cle["qid"])


def test_serendipity_zero_top_n_pur_genre_dominant(ctx):
    """Sans sérendipité, sur clusters bien séparés, le top-N est du genre aimé."""
    reco = _recommend(ctx, serendipity=0.0, top_n=10)
    qid_to_genre = ctx["qid_to_genre"]
    owner = ctx["owner_genre"]
    share = sum(1 for q in reco["qid"] if qid_to_genre[q] == owner) / len(reco)
    assert share >= 0.6


def test_serendipity_positive_introduit_hors_genre(ctx):
    """Avec serendipity>0, au moins un item hors du genre dominant apparaît."""
    owner = ctx["owner_genre"]
    qid_to_genre = ctx["qid_to_genre"]

    base = _recommend(ctx, serendipity=0.0, top_n=10)
    base_off = sum(1 for q in base["qid"] if qid_to_genre[q] != owner)

    ser = _recommend(ctx, serendipity=0.4, top_n=10)
    ser_off = sum(1 for q in ser["qid"] if qid_to_genre[q] != owner)

    # La sérendipité doit FAIRE ÉMERGER des items hors-genre.
    assert ser_off >= 1
    assert ser_off > base_off


def test_serendipity_conserve_longueur_et_unicite(ctx):
    for s in (0.0, 0.2, 0.4, 0.5):
        reco = _recommend(ctx, serendipity=s, top_n=10)
        assert len(reco) == 10, f"serendipity={s}"
        # Aucun doublon.
        assert len(set(reco["qid"])) == 10, f"serendipity={s}"


def test_serendipity_exclut_les_notes(ctx):
    owner = ctx["owner_genre"]
    liked = set(ctx["genre_to_qids"][owner][:3])
    reco = _recommend(ctx, serendipity=0.4, top_n=10)
    assert set(reco["qid"]).isdisjoint(liked)


def test_serendipity_deterministe(ctx):
    r1 = _recommend(ctx, serendipity=0.3, top_n=10)
    r2 = _recommend(ctx, serendipity=0.3, top_n=10)
    assert list(r1["qid"]) == list(r2["qid"])
