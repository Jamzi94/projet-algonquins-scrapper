import numpy as np
from movreco.model.evaluate import ndcg_at_k


def test_ndcg_perfect_order_is_one():
    y_true = [3, 2, 1]
    y_score = [3, 2, 1]
    assert abs(ndcg_at_k(y_true, y_score, k=3) - 1.0) < 1e-9


def test_ndcg_reverse_order_is_low():
    y_true = [3, 2, 1]
    y_score = [1, 2, 3]
    assert ndcg_at_k(y_true, y_score, k=3) < 1.0
