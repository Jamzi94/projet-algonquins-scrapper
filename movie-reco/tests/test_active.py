"""Tests de l'apprentissage actif (Équipe 4) : active.suggest_to_rate.

Échantillonnage du point le plus éloigné (farthest-point) sur des embeddings
synthétiques GROUPÉS en clusters bien séparés. On valide : l'exclusion des notés,
le fait que les suggestions s'éloignent de ce qui est déjà noté (couverture), le
déterminisme, la gestion du cas ``rated`` vide, et la pondération par popularité.

Pur numpy, aucun réseau, aucune dépendance lourde.
"""
from __future__ import annotations

import numpy as np

from movreco.model.active import suggest_to_rate


def _two_clusters(seed: int = 0, per: int = 5):
    """Deux clusters denses très éloignés sur l'axe x : 'A*' et 'B*'."""
    rng = np.random.default_rng(seed)
    cA = np.array([10.0, 0.0])
    cB = np.array([-10.0, 0.0])
    emb: list[np.ndarray] = []
    qids: list[str] = []
    for i in range(per):
        emb.append(cA + 0.01 * rng.normal(size=2))
        qids.append(f"A{i}")
    for i in range(per):
        emb.append(cB + 0.01 * rng.normal(size=2))
        qids.append(f"B{i}")
    return np.asarray(emb, dtype="float32"), qids


# --------------------------------------------------------------------------- #
# Exploration : s'éloigner des notés
# --------------------------------------------------------------------------- #
def test_suggestions_eloignees_des_notes():
    emb, qids = _two_clusters()
    # On a tout noté dans le cluster A : les suggestions doivent venir du cluster B.
    rated = [f"A{i}" for i in range(5)]
    sugg = suggest_to_rate(emb, qids, rated, n=3)
    assert len(sugg) == 3
    assert all(q.startswith("B") for q in sugg), sugg
    # Aucune suggestion notée.
    assert all(q not in set(rated) for q in sugg)


def test_premier_choix_le_plus_eloigne_du_cluster_note():
    """Avec un seul film noté, le 1er suggéré doit être dans le cluster opposé."""
    emb, qids = _two_clusters()
    rated = ["A0"]
    sugg = suggest_to_rate(emb, qids, rated, n=1)
    assert len(sugg) == 1
    assert sugg[0].startswith("B")


# --------------------------------------------------------------------------- #
# Couverture : les suggestions ne se concentrent pas sur un seul cluster
# --------------------------------------------------------------------------- #
def test_couverture_des_deux_clusters_sans_notes():
    emb, qids = _two_clusters()
    sugg = suggest_to_rate(emb, qids, [], n=4)
    assert len(sugg) == 4
    # Aucun doublon.
    assert len(set(sugg)) == 4
    # Le farthest-point doit toucher les DEUX clusters (couverture de l'espace).
    assert any(q.startswith("A") for q in sugg)
    assert any(q.startswith("B") for q in sugg)


# --------------------------------------------------------------------------- #
# Déterminisme
# --------------------------------------------------------------------------- #
def test_determinisme():
    emb, qids = _two_clusters()
    rated = ["A0", "A1"]
    s1 = suggest_to_rate(emb, qids, rated, n=4)
    s2 = suggest_to_rate(emb, qids, rated, n=4)
    assert s1 == s2


def test_determinisme_egalites_departagees_par_indice():
    """Sur des points équidistants, le départage suit l'indice croissant."""
    # 3 points équidistants d'un noté placé à l'origine ; égalité parfaite.
    emb = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [0.0, 0.0]], dtype="float32")
    qids = ["X0", "X1", "X2", "R"]
    # On note R (origine) : X0/X1/X2 sont à distance 1, égalité -> indice mini.
    sugg = suggest_to_rate(emb, qids, ["R"], n=1)
    assert sugg == ["X0"]


# --------------------------------------------------------------------------- #
# Exclusion des notés et bornes
# --------------------------------------------------------------------------- #
def test_exclut_toujours_les_notes():
    emb, qids = _two_clusters()
    rated = ["A0", "B0", "A1"]
    sugg = suggest_to_rate(emb, qids, rated, n=10)
    assert set(sugg).isdisjoint(set(rated))


def test_n_borne_le_nombre_de_suggestions():
    emb, qids = _two_clusters(per=5)  # 10 films
    rated = [f"A{i}" for i in range(5)]  # 5 notés -> 5 candidats restants
    sugg = suggest_to_rate(emb, qids, rated, n=100)
    # Au plus le nombre de candidats non notés disponibles.
    assert len(sugg) == 5
    assert len(set(sugg)) == 5


def test_rated_vide_renvoie_n_suggestions():
    emb, qids = _two_clusters(per=5)
    sugg = suggest_to_rate(emb, qids, [], n=4)
    assert len(sugg) == 4
    assert len(set(sugg)) == 4


def test_rated_none_traite_comme_vide():
    emb, qids = _two_clusters(per=3)
    sugg = suggest_to_rate(emb, qids, None, n=2)
    assert len(sugg) == 2


# --------------------------------------------------------------------------- #
# Cas dégradés
# --------------------------------------------------------------------------- #
def test_n_nul_renvoie_liste_vide():
    emb, qids = _two_clusters()
    assert suggest_to_rate(emb, qids, [], n=0) == []


def test_catalogue_vide_renvoie_liste_vide():
    assert suggest_to_rate(np.zeros((0, 2), dtype="float32"), [], [], n=5) == []


def test_tous_notes_renvoie_liste_vide():
    emb, qids = _two_clusters(per=2)  # 4 films
    sugg = suggest_to_rate(emb, qids, qids, n=5)
    assert sugg == []


# --------------------------------------------------------------------------- #
# Pondération par popularité
# --------------------------------------------------------------------------- #
def test_lambda_pop_favorise_les_populaires_sans_notes():
    """Avec lambda_pop=1, le 1er choix (sans notes) est le plus populaire."""
    emb, qids = _two_clusters(per=5)
    # Popularité alignée sur qids : un pic net sur B2.
    pop = np.ones(len(qids), dtype=float)
    idx_b2 = qids.index("B2")
    pop[idx_b2] = 1000.0
    sugg = suggest_to_rate(emb, qids, [], n=1, popularity=pop, lambda_pop=1.0)
    assert sugg == ["B2"]


def test_lambda_pop_defaut_0_pur_exploration():
    """Par défaut (lambda_pop=0), la sélection est purement géométrique."""
    emb, qids = _two_clusters()
    rated = [f"A{i}" for i in range(5)]
    pop = np.ones(len(qids), dtype=float)
    pop[qids.index("A0")] = 1000.0  # popularité sur un noté : sans effet
    sugg = suggest_to_rate(emb, qids, rated, n=3, popularity=pop, lambda_pop=0.0)
    # Exploration pure : on reste sur le cluster opposé (B*).
    assert all(q.startswith("B") for q in sugg)


def test_popularite_mauvaise_taille_ignoree():
    """Une popularité de taille incompatible est ignorée proprement."""
    emb, qids = _two_clusters(per=3)  # 6 films
    pop = np.ones(3, dtype=float)  # taille incorrecte
    # Ne doit pas lever : la pondération est simplement désactivée.
    sugg = suggest_to_rate(emb, qids, [], n=2, popularity=pop, lambda_pop=0.5)
    assert len(sugg) == 2


# --------------------------------------------------------------------------- #
# Alignement emb / qids
# --------------------------------------------------------------------------- #
def test_emb_qids_desalignes_leve_valueerror():
    emb = np.zeros((3, 4), dtype="float32")
    try:
        suggest_to_rate(emb, ["A", "B"], [], n=1)
    except ValueError:
        return
    raise AssertionError("ValueError attendue pour emb/qids désalignés")
