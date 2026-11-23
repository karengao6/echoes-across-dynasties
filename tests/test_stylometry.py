from statistics import mean, pvariance

import pytest

from echoes.stylometry import principal_components


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
