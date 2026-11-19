import pytest

from lattice.data.comparison import cp_interval, paired_comparison


def test_exact_binomial_endpoints():
    low, high = cp_interval(0, 60, 0.05)
    assert low == 0.0
    assert high == pytest.approx(1 - 0.025 ** (1 / 60))
    low, high = cp_interval(60, 60, 0.05)
    assert high == 1.0
    assert low == pytest.approx(0.025 ** (1 / 60))


def test_identical_pairs_do_not_prove_zero_risk():
    result = paired_comparison([True] * 60, [True] * 60)
    assert result["accuracy_loss_vs_baseline"] == 0
    assert result["accuracy_loss_interval95"][1] > 0.01
    assert result["mcnemar_exact_two_sided_p"] == 1.0
    assert not result["automatic_policy_qualification"]


def test_paired_discordance_direction_and_significance():
    result = paired_comparison([True] * 60, [False] * 6 + [True] * 54)
    assert result["baseline_only_correct"] == 6
    assert result["candidate_only_correct"] == 0
    assert result["accuracy_loss_vs_baseline"] == 0.1
    assert result["mcnemar_exact_two_sided_p"] == pytest.approx(0.03125)


@pytest.mark.parametrize("a,b", [([], []), ([True], []), ([1], [True])])
def test_invalid_pairs(a, b):
    with pytest.raises(ValueError):
        paired_comparison(a, b)
