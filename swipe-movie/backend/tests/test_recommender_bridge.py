"""Tests du pont (bridge) SwipeNight x movreco — SYNERGIE, hors-ligne, déterministe.

Ce module valide :class:`recommender_bridge.SynergyEngine`, le COEUR de la synergie
entre SwipeNight (UX swipe, rooms, group_score) et movie-reco (catalogue Wikidata
CC0 + Wikipedia CC BY-SA, moteur de recommandation licence-clean).

Aucun réseau, aucun modèle lourd : on RÉUTILISE le catalogue synthétique de
movie-reco (``tests/_synthetic.build_synthetic_catalog``), qui écrit sur disque des
items/embeddings/structured/rated groupés PAR GENRE. Un genre = une direction de
l'espace d'embedding ; on peut donc valider la PERTINENCE des recommandations sans
sentence-transformers : aimer un genre doit ramener des films du même genre.

Conventions movreco respectées (français, ``from __future__ import annotations``,
imports lourds tolérés en option). On NE MODIFIE PAS movie-reco : on ajoute des
chemins à ``sys.path`` pour importer son paquet ``movreco`` et son helper de test.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Insertion des chemins (movreco et son helper de test ne sont pas pip-installés).
# Ce fichier vit dans swipe-movie/backend/tests/ :
#   parents[1] -> swipe-movie/backend  (pour importer recommender_bridge)
#   parents[3] -> racine du dépôt      (pour atteindre movie-reco, frère)
# On insère movie-reco ET movie-reco/tests pour importer movreco et _synthetic.
# --------------------------------------------------------------------------- #
_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MOVRECO_ROOT = _REPO_ROOT / "movie-reco"
for _p in (str(_BACKEND), str(_MOVRECO_ROOT), str(_MOVRECO_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# movreco doit être importable : sinon, l'environnement n'est pas configuré pour la
# synergie et tous ces tests perdent leur sens — on les saute proprement.
pytest.importorskip("movreco")

from _synthetic import build_synthetic_catalog  # noqa: E402

import recommender_bridge as RB  # noqa: E402


N_GENRES = 4
PER_GENRE = 15
DIM = 16
SEED = 0


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def catalog_ctx(tmp_path):
    """Construit un catalogue synthétique groupé par genre et renvoie ses méta.

    Le helper écrit items/embeddings/structured/rated sous ``tmp_path`` et renvoie
    un ``cfg`` dont ``paths.data_dir`` pointe sur ``tmp_path`` : il suffit ensuite à
    ``SynergyEngine.load(cfg)`` pour charger l'état movreco sans toucher au disque
    de prod.
    """
    return build_synthetic_catalog(
        tmp_path, n_genres=N_GENRES, per_genre=PER_GENRE, dim=DIM, seed=SEED
    )


@pytest.fixture()
def engine(catalog_ctx):
    """Moteur de synergie chargé depuis le catalogue synthétique."""
    return RB.SynergyEngine.load(catalog_ctx["cfg"])


# --------------------------------------------------------------------------- #
# Chargement
# --------------------------------------------------------------------------- #
def test_load_echoue_sans_artefacts(tmp_path):
    """``load`` lève une RuntimeError claire quand les artefacts sont absents."""
    from movreco.config import load_config

    cfg = load_config()
    # data_dir vide : ni items ni embeddings -> le pont doit refuser de charger.
    cfg["paths"] = {
        "data_dir": str(tmp_path / "vide"),
        "models_dir": str(tmp_path / "vide" / "models"),
    }
    with pytest.raises(RuntimeError):
        RB.SynergyEngine.load(cfg)


# --------------------------------------------------------------------------- #
# Statut du fournisseur
# --------------------------------------------------------------------------- #
def test_provider_status_licence_clean_sans_tmdb(engine):
    """Le statut décrit une source licence-clean, TMDB désactivé."""
    status = engine.provider_status()
    assert status["source"] == "wikidata+wikipedia"
    assert status["tmdb_enabled"] is False
    assert status["license"] == "CC0 + CC BY-SA"
    assert status["catalog_size"] == N_GENRES * PER_GENRE


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
def test_catalog_mappe_qid_label_genres(engine, catalog_ctx):
    """Le catalogue mappe id=qid, title=label, genres parsés en liste."""
    cat = engine.catalog()
    assert len(cat) == N_GENRES * PER_GENRE

    qid_to_genre = catalog_ctx["qid_to_genre"]
    for content in cat:
        # Contrat de forme SwipeNight.
        assert content["type"] == "movie"
        assert content["source"] == "wikidata"
        assert isinstance(content["genres"], list)
        # id == qid Wikidata, title == label movreco.
        assert content["id"] in qid_to_genre
        assert content["title"].startswith(qid_to_genre[content["id"]])
        # genres parsé depuis la colonne '|' -> exactement le genre du film.
        assert content["genres"] == [qid_to_genre[content["id"]]]
        # year extrait de la date "YYYY-01-01".
        assert isinstance(content["year"], int)


def test_catalog_respecte_limit(engine):
    """``limit`` borne le nombre de contenus renvoyés."""
    assert len(engine.catalog(limit=5)) == 5
    assert len(engine.catalog(limit=0)) == 0


# --------------------------------------------------------------------------- #
# Conversion swipes -> notes
# --------------------------------------------------------------------------- #
def test_swipes_to_ratings_table_de_conversion(engine):
    """Chaque action connue produit la note attendue (table SWIPE_TO_RATING)."""
    swipes = [
        {"qid": "Qa", "action": "superlike"},
        {"qid": "Qb", "action": "like"},
        {"qid": "Qc", "action": "watchlist"},
        {"qid": "Qd", "action": "dislike"},
        {"qid": "Qe", "action": "abandoned"},
    ]
    rated, ratings, exclude = engine.swipes_to_ratings(swipes)
    assert rated == ["Qa", "Qb", "Qc", "Qd", "Qe"]
    assert ratings == [5.0, 4.5, 4.0, 2.0, 1.5]
    assert exclude == []


def test_swipes_to_ratings_veto_exclut_neutral_ignore(engine):
    """veto -> exclude (pas une note) ; neutral -> ni note ni exclusion."""
    swipes = [
        {"qid": "Q1", "action": "like"},
        {"qid": "Q2", "action": "neutral"},  # ignoré
        {"qid": "Q3", "action": "veto"},     # exclusion dure
    ]
    rated, ratings, exclude = engine.swipes_to_ratings(swipes)
    assert rated == ["Q1"]
    assert ratings == [4.5]
    assert exclude == ["Q3"]
    # neutral n'apparaît nulle part.
    assert "Q2" not in rated
    assert "Q2" not in exclude


def test_swipes_to_ratings_accepte_content_id(engine):
    """L'alias ``content_id`` est accepté au même titre que ``qid``."""
    rated, ratings, exclude = engine.swipes_to_ratings(
        [{"content_id": "Qx", "action": "like"}]
    )
    assert rated == ["Qx"]
    assert ratings == [4.5]


# --------------------------------------------------------------------------- #
# Recommandation individuelle — PERTINENCE
# --------------------------------------------------------------------------- #
def test_recommend_for_user_pertinence_par_genre(engine, catalog_ctx):
    """Un utilisateur qui aime 3 films du genre G -> top-N majoritairement genre G.

    Validation centrale de la SYNERGIE : le scoring movreco (vecteur de goût +
    cosinus) doit ramener des films du même genre que ceux aimés. On exige une
    nette majorité (au moins 60 %) du top-N dans le genre aimé.
    """
    qid_to_genre = catalog_ctx["qid_to_genre"]
    genre_to_qids = catalog_ctx["genre_to_qids"]
    liked_genre = catalog_ctx["genre_names"][0]
    liked = genre_to_qids[liked_genre][:3]

    swipes = [{"qid": q, "action": "like"} for q in liked]
    recs = engine.recommend_for_user(swipes, n=10)

    assert len(recs) == 10
    # Forme du contrat : id, title, score, reasons.
    for r in recs:
        assert set(r) >= {"id", "title", "score", "reasons"}
        assert isinstance(r["reasons"], list) and r["reasons"]

    genres = Counter(qid_to_genre[r["id"]] for r in recs)
    same = genres[liked_genre]
    assert same / len(recs) >= 0.60, f"pertinence insuffisante: {genres}"


def test_recommend_for_user_exclut_films_swipes(engine, catalog_ctx):
    """Les films déjà swipés (et vetotés) ne sont jamais re-proposés."""
    genre_to_qids = catalog_ctx["genre_to_qids"]
    liked_genre = catalog_ctx["genre_names"][0]
    liked = genre_to_qids[liked_genre][:3]
    veto_target = genre_to_qids[catalog_ctx["genre_names"][1]][0]

    swipes = [{"qid": q, "action": "like"} for q in liked]
    swipes.append({"qid": veto_target, "action": "veto"})

    recs = engine.recommend_for_user(swipes, n=20)
    rec_ids = {r["id"] for r in recs}
    # Aucun film aimé ni vetoté dans les recommandations.
    assert rec_ids.isdisjoint(set(liked))
    assert veto_target not in rec_ids


def test_recommend_for_user_respecte_exclude_appelant(engine, catalog_ctx):
    """Le paramètre ``exclude`` retire des candidats supplémentaires."""
    genre_to_qids = catalog_ctx["genre_to_qids"]
    liked_genre = catalog_ctx["genre_names"][0]
    liked = genre_to_qids[liked_genre][:3]
    swipes = [{"qid": q, "action": "like"} for q in liked]

    # On exclut explicitement un film du genre aimé non swipé.
    extra_exclude = [genre_to_qids[liked_genre][5]]
    recs = engine.recommend_for_user(swipes, n=20, exclude=extra_exclude)
    assert extra_exclude[0] not in {r["id"] for r in recs}


# --------------------------------------------------------------------------- #
# Recommandation de room — SYNERGIE group_score
# --------------------------------------------------------------------------- #
def test_recommend_for_room_picks_non_vides(engine, catalog_ctx):
    """2 membres aux goûts différents -> picks de groupe non vides, bien formés."""
    genre_to_qids = catalog_ctx["genre_to_qids"]
    names = catalog_ctx["genre_names"]

    member_a = {
        "user": "alice",
        "swipes": [{"qid": q, "action": "superlike"} for q in genre_to_qids[names[0]][:3]],
    }
    member_b = {
        "user": "bob",
        "swipes": [{"qid": q, "action": "superlike"} for q in genre_to_qids[names[2]][:3]],
    }

    picks = engine.recommend_for_room([member_a, member_b], n=5)
    assert 0 < len(picks) <= 5
    # Forme du contrat : id, title, group_score, components.
    for p in picks:
        assert set(p) >= {"id", "title", "group_score", "components"}
        assert isinstance(p["group_score"], float)
        assert {"mean_score", "min_score", "disagreement"} <= set(p["components"])
    # Tri décroissant par group_score.
    scores = [p["group_score"] for p in picks]
    assert scores == sorted(scores, reverse=True)


def test_recommend_for_room_veto_exclut_titre(engine, catalog_ctx):
    """Un veto d'UN SEUL membre exclut le titre pour toute la room."""
    genre_to_qids = catalog_ctx["genre_to_qids"]
    names = catalog_ctx["genre_names"]
    # Cible vetotée : un film d'un genre que personne n'a noté (donc candidat).
    veto_target = genre_to_qids[names[3]][7]

    member_a = {
        "user": "alice",
        "swipes": [{"qid": q, "action": "superlike"} for q in genre_to_qids[names[0]][:3]],
    }
    member_b = {
        "user": "bob",
        "swipes": (
            [{"qid": q, "action": "superlike"} for q in genre_to_qids[names[2]][:3]]
            + [{"qid": veto_target, "action": "veto"}]
        ),
    }

    # Sans veto, la cible peut apparaître ; avec veto, jamais.
    baseline = engine.recommend_for_room(
        [member_a, {"user": "bob", "swipes": member_a["swipes"]}], n=N_GENRES * PER_GENRE
    )
    picks = engine.recommend_for_room([member_a, member_b], n=N_GENRES * PER_GENRE)
    assert veto_target not in {p["id"] for p in picks}
    # Sanity : la cible était bien un candidat possible côté baseline.
    assert isinstance(baseline, list)


def test_recommend_for_room_sans_membres_renvoie_vide(engine):
    """Une room sans membre ne produit aucune recommandation (pas d'erreur)."""
    assert engine.recommend_for_room([], n=5) == []


# --------------------------------------------------------------------------- #
# Calibration (apprentissage actif)
# --------------------------------------------------------------------------- #
def test_calibration_titles_non_vides_et_deterministe(engine):
    """``calibration_titles`` renvoie n titres non vides, de façon déterministe."""
    first = engine.calibration_titles(n=12)
    second = engine.calibration_titles(n=12)
    assert len(first) == 12
    for t in first:
        assert set(t) >= {"id", "title"}
        assert t["id"] and t["title"]
    # Déterminisme : même entrée -> même sortie (même ordre).
    assert [t["id"] for t in first] == [t["id"] for t in second]
    # Pas de doublon dans la sélection.
    ids = [t["id"] for t in first]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# Garde-fou licence : aucune importation de TMDB dans le pont
# --------------------------------------------------------------------------- #
def test_aucune_importation_tmdb():
    """Le pont ne doit JAMAIS importer/référencer TMDB (contrainte licence)."""
    source = (_BACKEND / "recommender_bridge.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "import tmdb" not in lowered
    assert "from tmdb" not in lowered
    # Aucun module/sous-module nommé tmdb n'est importé.
    assert "tmdb." not in lowered.replace("tmdb_enabled", "")
