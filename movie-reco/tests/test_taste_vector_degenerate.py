"""Tests du contrat signed_taste_vector pour les cas dégénérés.

Le contrat (Équipe 1) impose : ne JAMAIS renvoyer un vecteur nul si `emb_rated`
est non vide ; repli sur la moyenne normalisée des embeddings quand la variance
des notes est ~0 (notes toutes égales ou une seule note).
"""
from __future__ import annotations

import numpy as np

from movreco.model.taste_vector import signed_taste_vector, cosine_scores


def test_notes_toutes_egales_vecteur_non_nul_et_norme_un():
    emb = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], dtype="float32")
    ratings = [7, 7, 7]  # variance ~0

    v = signed_taste_vector(emb, ratings)

    norm = np.linalg.norm(v)
    assert norm > 0  # NON nul
    assert abs(norm - 1.0) < 1e-5  # normalisé


def test_une_seule_note_vecteur_non_nul():
    emb = np.array([[3.0, 4.0]], dtype="float32")
    ratings = [9]  # une seule note -> pondération (note - moyenne) = 0

    v = signed_taste_vector(emb, ratings)

    norm = np.linalg.norm(v)
    assert norm > 0
    assert abs(norm - 1.0) < 1e-5
    # repli sur la moyenne normalisée : direction = [3,4]/5
    np.testing.assert_allclose(v, np.array([0.6, 0.8], dtype="float32"), atol=1e-5)


def test_repli_pointe_vers_la_moyenne_des_films_notes():
    # notes égales -> le vecteur doit être proche de la moyenne des embeddings
    emb = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype="float32")
    ratings = [5, 5, 5]

    v = signed_taste_vector(emb, ratings)
    scores = cosine_scores(v, emb)
    # la majorité pointe vers [1,0], donc les films [1,0] scorent mieux que [0,1]
    assert scores[0] > scores[2]
    assert scores[1] > scores[2]


def test_cas_normal_pointe_vers_le_film_aime():
    emb = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    ratings = [10, 0]  # aime le 1er, déteste le 2e

    v = signed_taste_vector(emb, ratings)
    scores = cosine_scores(v, emb)
    assert scores[0] > scores[1]
    assert abs(np.linalg.norm(v) - 1.0) < 1e-5


def test_emb_vide_renvoie_vecteur_nul():
    # cas limite : pas d'embedding noté -> vecteur de zéros (géré par le pipeline)
    emb = np.zeros((0, 4), dtype="float32")
    ratings = []

    v = signed_taste_vector(emb, ratings)
    assert v.shape == (4,)
    assert np.linalg.norm(v) == 0.0
