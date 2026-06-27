import numpy as np
from movreco.model.taste_vector import signed_taste_vector, cosine_scores


def test_taste_vector_is_normalized():
    emb = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    ratings = [10, 0]
    v = signed_taste_vector(emb, ratings)
    assert abs(np.linalg.norm(v) - 1.0) < 1e-5


def test_taste_points_toward_liked():
    emb = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    ratings = [10, 0]  # aime le 1er, deteste le 2e
    v = signed_taste_vector(emb, ratings)
    scores = cosine_scores(v, emb)
    assert scores[0] > scores[1]
