"""Paired quality differences with conservative finite-sample uncertainty.

The interval bounds discordant outcome probabilities separately with exact
Clopper-Pearson intervals at Bonferroni-adjusted coverage, then subtracts them.
Unlike a naive bootstrap, all observed pairs agreeing does not imply zero risk.
"""

import math


def binomial_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0
    logs = [
        math.lgamma(n + 1)
        - math.lgamma(i + 1)
        - math.lgamma(n - i + 1)
        + i * math.log(p)
        + (n - i) * math.log1p(-p)
        for i in range(k + 1)
    ]
    maximum = max(logs)
    return min(1.0, math.exp(maximum) * sum(math.exp(v - maximum) for v in logs))


def cp_interval(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if not 0 <= k <= n or n <= 0 or not 0 < alpha < 1:
        raise ValueError("Invalid binomial observations or alpha")

    def invert(index, target):
        low, high = 0.0, 1.0
        for _ in range(70):
            mid = (low + high) / 2
            if binomial_cdf(index, n, mid) > target:
                low = mid
            else:
                high = mid
        return (low + high) / 2

    lower = 0.0 if k == 0 else invert(k - 1, 1 - alpha / 2)
    upper = 1.0 if k == n else invert(k, alpha / 2)
    return lower, upper


def paired_comparison(baseline: list[bool], candidate: list[bool]) -> dict:
    if (
        len(baseline) != len(candidate)
        or not baseline
        or any(type(x) is not bool for x in baseline + candidate)
    ):
        raise ValueError(
            "Require equally sized nonempty actual-boolean paired observations"
        )
    n = len(baseline)
    losses = sum(a and not b for a, b in zip(baseline, candidate, strict=True))
    wins = sum(b and not a for a, b in zip(baseline, candidate, strict=True))
    loss_interval = cp_interval(losses, n, 0.025)
    win_interval = cp_interval(wins, n, 0.025)
    discordant = losses + wins
    exact_p = (
        min(1.0, 2 * binomial_cdf(min(losses, wins), discordant, 0.5))
        if discordant
        else 1.0
    )
    return {
        "paired_records": n,
        "baseline_only_correct": losses,
        "candidate_only_correct": wins,
        "accuracy_loss_vs_baseline": (losses - wins) / n,
        "accuracy_loss_interval95": [
            loss_interval[0] - win_interval[1],
            loss_interval[1] - win_interval[0],
        ],
        "interval_method": "Conservative paired discordance interval: Bonferroni exact Clopper-Pearson bounds",
        "mcnemar_exact_two_sided_p": exact_p,
        "multiple_comparison_adjusted": False,
        "automatic_policy_qualification": False,
    }
