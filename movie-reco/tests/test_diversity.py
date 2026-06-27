import numpy as np
from movreco.recommend.diversity import mmr, popularity_penalty, minmax


def test_mmr_returns_k():
    emb = np.eye(5, dtype="float32")
    cand = list(range(5))
    rel = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
    chosen, local = mmr(cand, rel, emb, k=3, lam=0.7)
    assert len(chosen) == 3
    assert len(set(chosen)) == 3


def test_mmr_prefers_relevance_with_lambda_one():
    emb = np.eye(3, dtype="float32")
    cand = [0, 1, 2]
    rel = np.array([0.1, 0.9, 0.5])
    chosen, _ = mmr(cand, rel, emb, k=1, lam=1.0)
    assert chosen[0] == 1


def test_popularity_penalty_reduces_scores():
    scores = np.array([1.0, 1.0])
    pop = np.array([0.0, 1000.0])
    out = popularity_penalty(scores, pop, weight=0.5)
    assert out[1] < out[0]


def test_minmax_range():
    out = minmax([1, 2, 3])
    assert out.min() == 0.0 and out.max() == 1.0
