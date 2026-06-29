"""Tests de combine.feature_matrix : alignement, qid manquant, dimensions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from movreco.features.combine import feature_matrix


def _setup():
    items = pd.DataFrame({"qid": ["Q1", "Q2", "Q3"]})
    # emb aligné sur les lignes de items : emb[i] <-> items["qid"][i]
    emb = np.array(
        [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        dtype="float32",
    )
    # structured indexé par qid, 4 colonnes
    structured = pd.DataFrame(
        [
            [1.0, 0.0, 0.0, 1.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 1.0],
        ],
        index=pd.Index(["Q1", "Q2", "Q3"], name="qid"),
        columns=["a", "b", "c", "d"],
    ).astype("float32")
    return items, emb, structured


def test_dimension_attendue_struct_plus_emb():
    items, emb, structured = _setup()
    struct_dim = structured.shape[1]  # 4
    emb_dim = emb.shape[1]  # 2

    mat = feature_matrix(["Q1", "Q2", "Q3"], items, emb, structured)

    assert mat.shape == (3, struct_dim + emb_dim)
    assert mat.dtype == np.float32


def test_alignement_correct_struct_puis_emb():
    items, emb, structured = _setup()
    mat = feature_matrix(["Q2"], items, emb, structured)

    # ordre : [structuré | embedding]
    expected = np.concatenate(
        [structured.loc["Q2"].values, emb[1]]
    ).astype("float32")
    np.testing.assert_array_equal(mat[0], expected)


def test_qid_manquant_donne_vecteur_de_zeros():
    items, emb, structured = _setup()
    struct_dim = structured.shape[1]
    emb_dim = emb.shape[1]

    # QZZ n'est ni dans items ni dans structured -> tout à zéro
    mat = feature_matrix(["QZZ"], items, emb, structured)

    assert mat.shape == (1, struct_dim + emb_dim)
    np.testing.assert_array_equal(mat[0], np.zeros(struct_dim + emb_dim, dtype="float32"))


def test_qid_present_dans_items_mais_pas_structured():
    # struct manquant -> zéros côté structuré, embedding conservé.
    items = pd.DataFrame({"qid": ["Q1", "Q2"]})
    emb = np.array([[5.0, 6.0], [7.0, 8.0]], dtype="float32")
    structured = pd.DataFrame(
        [[1.0, 2.0]],
        index=pd.Index(["Q1"], name="qid"),
        columns=["x", "y"],
    ).astype("float32")

    mat = feature_matrix(["Q2"], items, emb, structured)

    expected = np.concatenate([np.zeros(2, dtype="float32"), emb[1]])
    np.testing.assert_array_equal(mat[0], expected)


def test_ordre_des_lignes_suit_qids_demandes():
    items, emb, structured = _setup()
    mat = feature_matrix(["Q3", "Q1"], items, emb, structured)

    row0 = np.concatenate([structured.loc["Q3"].values, emb[2]]).astype("float32")
    row1 = np.concatenate([structured.loc["Q1"].values, emb[0]]).astype("float32")
    np.testing.assert_array_equal(mat[0], row0)
    np.testing.assert_array_equal(mat[1], row1)
