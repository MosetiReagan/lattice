import random
from collections import Counter

import pytest

from lattice.optimizations.speculative.compatibility import tokenizer_fingerprint
from lattice.optimizations.speculative.sampling import draw, generate, verify_block


def test_all_accept_and_correct_bonus():
    rng = random.Random(4)
    result = verify_block([0, 1], [[1, 0], [0, 1]], [[1, 0], [0, 1], [0, 1]], rng)
    assert result.emitted == (0, 1, 1) and result.accepted == 2 and result.bonus


def test_rejection_uses_residual_not_target():
    result = verify_block([1], [[0, 1]], [[1, 0], [0, 1]], random.Random(0))
    assert result.emitted == (0,) and result.rejected == 1
    with pytest.raises(ValueError):
        verify_block([0], [[0, 1]], [[1, 0], [0, 1]], random.Random())


def test_stochastic_first_token_matches_analytical_target():
    rng = random.Random(118)
    p, q = [0.7, 0.2, 0.1], [0.05, 0.15, 0.8]
    outcomes = Counter()
    for _ in range(40000):
        proposal = draw(q, rng)
        outcomes[verify_block([proposal], [q], [p, p], rng).emitted[0]] += 1
    for i, expected in enumerate(p):
        assert outcomes[i] / 40000 == pytest.approx(expected, abs=0.01)


class FiniteModel:
    def __init__(self, first, second):
        self.first, self.second = first, second

    async def next_distribution(self, history):
        return self.first if not history else self.second[history[-1]]

    async def verify_batch(self, history, proposals):
        return [
            await self.next_distribution(history + proposals[:i])
            for i in range(len(proposals) + 1)
        ]


async def test_history_dependent_joint_distribution_and_limits():
    target = FiniteModel([0.6, 0.4], [[0.9, 0.1], [0.2, 0.8]])
    draft = FiniteModel([0.1, 0.9], [[0.5, 0.5], [0.7, 0.3]])
    rng = random.Random(61)
    outcomes = Counter()
    for _ in range(12000):
        result = tuple([t async for t in generate(draft, target, (), 2, 2, rng)])
        assert len(result) == 2
        outcomes[result] += 1
    for pair, expected in {
        (0, 0): 0.54,
        (0, 1): 0.06,
        (1, 0): 0.08,
        (1, 1): 0.32,
    }.items():
        assert outcomes[pair] / 12000 == pytest.approx(expected, abs=0.02)
    result = [
        t
        async for t in generate(
            draft, target, (), 20, 4, random.Random(1), frozenset({0, 1})
        )
    ]
    assert len(result) == 1


def test_metadata_parser_rejects_invalid_artifacts(tmp_path):
    p = tmp_path / "bad.gguf"
    p.write_bytes(b"not a model")
    with pytest.raises(ValueError):
        tokenizer_fingerprint(p)
