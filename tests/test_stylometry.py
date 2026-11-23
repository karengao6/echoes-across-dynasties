from collections import Counter
from statistics import mean, pvariance

import numpy as np
import pytest

from echoes.stylometry import character_pca, principal_components


def test_pca_orders_scores_by_variance_and_drops_constant_column():
    scores, variance = principal_components([
        (-1, -1, 1, 7),
        (-1, -1, -1, 7),
        (1, 1, 1, 7),
        (1, 1, -1, 7),
    ])
    first, second = zip(*scores)
    assert variance == pytest.approx([2 / 3, 1 / 3])
    assert [pvariance(first), pvariance(second)] == pytest.approx([2, 1])
    assert mean(x * y for x, y in scores) == pytest.approx(0)


def test_pca_rejects_a_sample_with_fewer_than_two_components():
    with pytest.raises(ValueError, match="at least two varying components"):
        principal_components([(1,), (2,), (3,)])


def test_weighted_pca_centers_and_diagonalizes_the_weighted_scores():
    rows = [(-1, -1), (-1, 1), (1, 0), (3, 1), (4, 1)]
    weights = [1 / 4, 1 / 4, 1 / 6, 1 / 6, 1 / 6]
    scores, variance = principal_components(rows, weights)
    _, equal_variance = principal_components(rows)
    assert np.average(scores, axis=0, weights=weights) == pytest.approx([0, 0])
    first, second = np.asarray(scores).T
    assert np.average(first * second, weights=weights) == pytest.approx(0)
    assert variance != pytest.approx(equal_variance)


def test_character_pca_recovers_frequency_contrasts_and_loadings():
    counts = [
        Counter({"山": 25 + x, "水": 25 - x, "月": 25 + y, "風": 25 - y})
        for x, y in [(-10, -5), (-10, 5), (10, -5), (10, 5)]
    ]
    view = character_pca(counts)
    assert view["variance"] == pytest.approx([0.8, 0.2])
    for axis, expected in enumerate([{"山", "水"}, {"月", "風"}]):
        loadings = view["loadings"][axis]
        char1, weight1 = loadings["positive"][0]
        char2, weight2 = loadings["negative"][0]
        assert {char1, char2} == expected
        assert weight1 == pytest.approx(-weight2)
        for poet, scores in zip(counts, view["scores"]):
            expected_score = (poet[char1] - poet[char2]) * 10 * weight1
            assert scores[axis] == pytest.approx(expected_score)


def test_character_pca_flags_a_sample_without_a_shared_vocabulary():
    view = character_pca([Counter("山"), Counter("水"), Counter("月")])
    assert view["vocabularySize"] == 0
    assert "unavailable" in view
