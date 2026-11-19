"""Speculative sampling with acceptance p/q and residual max(p-q, 0).

Inputs are FULL transformed probability distributions with identical token IDs.
This reference is independent of the llama.cpp serving adapter. No claim that
its stochastic correctness transfers to a third-party backend is implied.
"""

import math
import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol


def distribution(values: Sequence[float]) -> tuple[float, ...]:
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("Probabilities must be finite and nonnegative")
    total = math.fsum(values)
    if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("Expected a normalized full distribution")
    return tuple(x / total for x in values)


def draw(probabilities: Sequence[float], rng: random.Random) -> int:
    probabilities = distribution(probabilities)
    cutoff, total = rng.random(), 0.0
    last_positive = None
    for token, probability in enumerate(probabilities):
        total += probability
        if probability > 0:
            last_positive = token
        if cutoff < total:
            return token
    # Only compensates a floating-point cumulative-sum gap, never assigns mass to zeros.
    return last_positive


@dataclass(frozen=True)
class Verification:
    emitted: tuple[int, ...]
    accepted: int
    rejected: int
    bonus: bool


def verify_block(
    proposals: Sequence[int],
    draft: Sequence[Sequence[float]],
    target: Sequence[Sequence[float]],
    rng: random.Random,
) -> Verification:
    if (
        not proposals
        or len(draft) != len(proposals)
        or len(target) != len(proposals) + 1
    ):
        raise ValueError(
            "Need k proposals, k draft distributions and k+1 target distributions"
        )
    p_all = [distribution(p) for p in target]
    q_all = [distribution(q) for q in draft]
    vocab = len(p_all[0])
    if any(len(p) != vocab for p in [*p_all, *q_all]):
        raise ValueError("Draft and target vocabularies must match exactly")
    accepted = []
    for token, p, q in zip(proposals, p_all, q_all, strict=False):
        if not 0 <= token < vocab or q[token] == 0:
            raise ValueError("Draft proposal has zero probability or invalid token ID")
        if rng.random() < min(1.0, p[token] / q[token]):
            accepted.append(token)
        else:
            residual = [max(a - b, 0.0) for a, b in zip(p, q, strict=True)]
            mass = math.fsum(residual)
            if mass <= 0:
                raise ArithmeticError("Impossible rejection: residual has zero mass")
            corrected = draw([value / mass for value in residual], rng)
            return Verification((*accepted, corrected), len(accepted), 1, False)
    return Verification((*accepted, draw(p_all[-1], rng)), len(accepted), 0, True)


class DistributionModel(Protocol):
    async def next_distribution(self, history: tuple[int, ...]) -> Sequence[float]: ...
    async def verify_batch(
        self, history: tuple[int, ...], proposals: tuple[int, ...]
    ) -> Sequence[Sequence[float]]: ...


async def generate(
    draft: DistributionModel,
    target: DistributionModel,
    prompt: tuple[int, ...],
    max_tokens: int,
    draft_tokens: int,
    rng: random.Random,
    eos: frozenset[int] = frozenset(),
) -> AsyncIterator[int]:
    if max_tokens < 0 or draft_tokens < 1:
        raise ValueError("Invalid token limits")
    history, generated = prompt, 0
    while generated < max_tokens:
        proposals, probabilities = [], []
        for _ in range(min(draft_tokens, max_tokens - generated)):
            q = distribution(await draft.next_distribution(history + tuple(proposals)))
            token = draw(q, rng)
            proposals.append(token)
            probabilities.append(q)
            if token in eos:
                break
        result = verify_block(
            proposals,
            probabilities,
            await target.verify_batch(history, tuple(proposals)),
            rng,
        )
        for token in result.emitted:
            if generated == max_tokens:
                return
            history += (token,)
            generated += 1
            yield token
            if token in eos:
                return
