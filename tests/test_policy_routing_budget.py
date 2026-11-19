from dataclasses import replace

import pytest

from lattice.controller.policy import Features, PathEvidence, RuleController
from lattice.routing.router import ModelCandidate, route
from lattice.scheduler.budget import Budget, ResourceSnapshot, feasible
from lattice.types import LatticeError


def evidence(strategy="standard", latency=100):
    return PathEvidence(
        strategy,
        "model",
        "backend",
        128,
        2048,
        32,
        latency,
        1536,
        90,
        3,
        0,
        True,
        "proof",
    )


def features():
    return Features(512, 16, 500, "model", "backend", 0.0, 0)


def resources():
    return ResourceSnapshot(7000, 2048, 0)


def test_controller_requires_baseline_and_complete_quality_evidence():
    standard = evidence()
    cached = evidence("cached", 25)
    controller = RuleController([standard, cached])
    assert controller.choose(features(), Budget(16), resources()).strategy == "cached"
    assert (
        controller.choose(features(), Budget(16), resources(), "standard").strategy
        == "standard"
    )
    for bad in [
        replace(cached, greedy_mismatches=1),
        replace(cached, sessions=1),
        replace(cached, quality_qualified=False),
        replace(cached, model_sha256="other"),
    ]:
        assert (
            RuleController([standard, bad])
            .choose(features(), Budget(16), resources())
            .strategy
            == "standard"
        )
    assert (
        RuleController([cached]).choose(features(), Budget(16), resources()).strategy
        == "standard"
    )
    assert (
        controller.choose(
            replace(features(), temperature=0.7), Budget(16), resources()
        ).strategy
        == "standard"
    )
    assert (
        controller.choose(
            replace(features(), reusable_prefix_tokens=0), Budget(16), resources()
        ).strategy
        == "standard"
    )


def test_budget_hard_limits_and_unknowns():
    assert not feasible(None, 10, Budget(16), resources())[0]
    assert not feasible(
        2048, None, Budget(16, max_estimated_compute_ms=10), resources()
    )[0]
    assert not feasible(2048, 10, Budget(16, max_memory_mb=1024), resources())[0]
    with pytest.raises(ValueError):
        Budget(513)
    with pytest.raises(LatticeError):
        RuleController([evidence()]).choose(features(), Budget(8), resources())
    with pytest.raises(LatticeError):
        RuleController([]).choose(
            features(), Budget(16, max_memory_mb=100), resources()
        )


def test_router_requires_task_evidence_and_preserves_identity():
    candidates = [
        ModelCandidate("small", frozenset({"json"}), False, 10, 500, "proof"),
        ModelCandidate("large", frozenset({"json"}), True, 30, 2000, "proof"),
    ]
    assert route("large", candidates).model_id == "large"
    assert (
        route("balanced", candidates, alias="balanced", task_class="json").model_id
        == "large"
    )
    with pytest.raises(LatticeError):
        route("balanced", candidates, alias="balanced", task_class="math")
    with pytest.raises(LatticeError):
        route("missing", candidates)
