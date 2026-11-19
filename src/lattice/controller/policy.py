"""Pure policy evaluation: unknown/experimental paths cannot override constraints."""

import math
from dataclasses import dataclass

from lattice.scheduler.budget import Budget, ResourceSnapshot, feasible
from lattice.types import LatticeError

POLICY_VERSION = "rules-1"


@dataclass(frozen=True)
class Features:
    input_tokens: int
    output_limit: int
    reusable_prefix_tokens: int
    model_sha256: str
    backend_sha256: str
    temperature: float
    queue_depth: int
    prompt_sha256: str | None = None
    threads: int = 4
    cpu_fingerprint: str | None = None


@dataclass(frozen=True)
class PathEvidence:
    strategy: str
    model_sha256: str
    backend_sha256: str
    input_min: int
    input_max: int
    max_output_tokens: int
    median_latency_ms: float
    memory_bound_mb: int
    trials: int
    sessions: int
    greedy_mismatches: int
    quality_qualified: bool
    evidence_id: str
    qualified_prompt_sha256: frozenset[str] | None = None
    threads: int | None = None
    cpu_fingerprint: str | None = None

    def __post_init__(self):
        if not math.isfinite(self.median_latency_ms) or self.median_latency_ms <= 0:
            raise ValueError("Profile latency must be positive and finite")
        if (
            self.memory_bound_mb < 1
            or self.input_min < 0
            or self.input_max < self.input_min
        ):
            raise ValueError("Invalid profile resource bounds")
        if (
            min(self.trials, self.sessions, self.greedy_mismatches) < 0
            or self.greedy_mismatches > self.trials
        ):
            raise ValueError("Invalid profile evidence counts")


@dataclass(frozen=True)
class Decision:
    strategy: str
    reason: str
    evidence_id: str | None
    evidence_coverage: float
    policy_version: str = POLICY_VERSION
    estimated_latency_ms: float | None = None
    latency_target_met: bool | None = None


class RuleController:
    def __init__(self, evidence: list[PathEvidence]):
        self.evidence = tuple(evidence)

    def choose(
        self,
        features: Features,
        budget: Budget,
        resources: ResourceSnapshot,
        explicit: str = "adaptive",
        preference: str = "balanced",
    ) -> Decision:
        if preference == "lowest_compute":
            raise LatticeError(
                "A validated compute-cost model is not available; choose balanced or lowest_latency",
                422,
                "compute_model_unavailable",
            )
        if features.output_limit > budget.max_output_tokens:
            raise LatticeError(
                "Output exceeds hard token budget", 422, "budget_infeasible"
            )
        if (
            explicit == "standard"
            and budget.max_memory_mb is None
            and budget.max_estimated_compute_ms is None
        ):
            return Decision(
                "standard", "Explicit standard strategy preserved", None, 1.0
            )
        eligible = []
        for profile in self.evidence:
            if profile.threads is not None and features.threads != profile.threads:
                continue
            if (
                profile.cpu_fingerprint is not None
                and features.cpu_fingerprint != profile.cpu_fingerprint
            ):
                continue
            if (
                profile.qualified_prompt_sha256 is not None
                and features.prompt_sha256 not in profile.qualified_prompt_sha256
            ):
                continue
            if (
                profile.model_sha256 != features.model_sha256
                or profile.backend_sha256 != features.backend_sha256
            ):
                continue
            if not profile.input_min <= features.input_tokens <= profile.input_max:
                continue
            if features.output_limit > profile.max_output_tokens:
                continue
            if (
                not profile.quality_qualified
                or profile.greedy_mismatches
                or profile.trials < 30
                or profile.sessions < 3
            ):
                continue
            # Stochastic serving preservation has not been qualified for optimized paths.
            if profile.strategy != "standard" and features.temperature != 0:
                continue
            if profile.strategy == "cached" and features.reusable_prefix_tokens < 64:
                continue
            if explicit != "adaptive" and profile.strategy != explicit:
                continue
            allowed, _ = feasible(
                profile.memory_bound_mb, profile.median_latency_ms, budget, resources
            )
            if allowed:
                eligible.append(profile)
        if not eligible:
            if (
                budget.max_memory_mb is not None
                or budget.max_estimated_compute_ms is not None
            ):
                raise LatticeError(
                    "No measured path satisfies the hard resource budget",
                    422,
                    "budget_infeasible",
                )
            return Decision(
                "standard", "No qualified measured compatible optimization", None, 0.0
            )
        chosen = min(
            eligible,
            key=lambda p: (
                (p.memory_bound_mb, p.median_latency_ms, p.strategy)
                if preference == "lowest_memory"
                else (p.median_latency_ms, p.strategy)
            ),
        )
        standard = [p for p in eligible if p.strategy == "standard"]
        if chosen.strategy != "standard" and not standard:
            return Decision(
                "standard", "No comparable measured standard path", None, 0.0
            )
        return Decision(
            chosen.strategy,
            "Minimum measured latency among compatible quality-qualified paths",
            chosen.evidence_id,
            min(1.0, chosen.trials / 90),
            POLICY_VERSION,
            chosen.median_latency_ms,
            None
            if budget.latency_budget_ms is None
            else chosen.median_latency_ms <= budget.latency_budget_ms,
        )
