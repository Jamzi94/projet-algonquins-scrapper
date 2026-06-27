"""Tests du contrat combine.align_embeddings (réalignement emb -> items["qid"])."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from movreco.features.combine import align_embeddings


def _items(qids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"qid": qids})


def test_reordonne_quand_emb_ids_permute():
    # emb_ids dans un ordre différent de items["qid"] : on doit réaligner.
    emb = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], dtype="float32")
    emb_ids = ["Q3", "Q1", "Q2"]  # emb[0]->Q3, emb[1]->Q1, emb[2]->Q2
    items = _items(["Q1", "Q2", "Q3"])

    out = align_embeddings(emb, emb_ids, items)

    assert out.shape == (3, 2)
    # ligne i doit correspondre à items["qid"][i]
    np.testing.assert_array_equal(out[0], emb[1])  # Q1
    np.testing.assert_array_equal(out[1], emb[2])  # Q2
    np.testing.assert_array_equal(out[2], emb[0])  # Q3


def test_sous_ensemble_et_doublon_de_qid():
    # emb_ids peut contenir plus d'entrées que items ; un même qid peut
    # apparaître plusieurs fois dans items et doit être dupliqué correctement.
    emb = np.array([[10.0], [20.0], [30.0]], dtype="float32")
    emb_ids = ["Q1", "Q2", "Q3"]
    items = _items(["Q3", "Q1", "Q1"])

    out = align_embeddings(emb, emb_ids, items)

    assert out.shape == (3, 1)
    np.testing.assert_array_equal(out[0], emb[2])  # Q3
    np.testing.assert_array_equal(out[1], emb[0])  # Q1
    np.testing.assert_array_equal(out[2], emb[0])  # Q1 (doublon)


def test_qid_absent_de_emb_ids_leve_valueerror():
    emb = np.array([[1.0], [2.0]], dtype="float32")
    emb_ids = ["Q1", "Q2"]
    items = _items(["Q1", "Q999"])  # Q999 absent de emb_ids

    with pytest.raises(ValueError) as exc:
        align_embeddings(emb, emb_ids, items)
    # message en français mentionnant la resynchronisation
    assert "désynchronisés" in str(exc.value)
    assert "movreco embed" in str(exc.value)


def test_emb_ids_none_longueur_coherente_renvoie_emb():
    emb = np.array([[1.0], [2.0], [3.0]], dtype="float32")
    items = _items(["Q1", "Q2", "Q3"])

    out = align_embeddings(emb, None, items)
    # renvoyé tel quel
    assert out is emb


def test_emb_ids_none_longueur_incoherente_leve_valueerror():
    emb = np.array([[1.0], [2.0]], dtype="float32")  # 2 lignes
    items = _items(["Q1", "Q2", "Q3"])  # 3 items

    with pytest.raises(ValueError) as exc:
        align_embeddings(emb, None, items)
    assert "désynchronisés" in str(exc.value)
