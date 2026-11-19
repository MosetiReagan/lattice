"""Hard resource feasibility and explicit unknown-cost handling."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    max_output_tokens: int
    max_memory_mb: int | None = None
    latency_budget_ms: float | None = None
    max_estimated_compute_ms: float | None = None

    def __post_init__(self):
        if not 1 <= self.max_output_tokens <= 512:
            raise ValueError("Output token limit must be 1..512")
        if self.max_memory_mb is not None and self.max_memory_mb < 1:
            raise ValueError("Memory limit must be positive")
        for value in (self.latency_budget_ms, self.max_estimated_compute_ms):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError("Budgets must be positive and finite")


@dataclass(frozen=True)
class ResourceSnapshot:
    available_memory_mb: int
    host_reserve_mb: int
    queue_depth: int
    gpu_available: bool = False
    gpu_memory_mb: int | None = None
    gpu_utilization: float | None = None


def feasible(
    memory_upper_mb: int | None,
    estimated_compute_ms: float | None,
    budget: Budget,
    resources: ResourceSnapshot,
) -> tuple[bool, str]:
    if memory_upper_mb is None:
        return False, "Unknown memory bound"
    if memory_upper_mb > max(
        0, resources.available_memory_mb - resources.host_reserve_mb
    ):
        return False, "Insufficient available host memory after reserve"
    if budget.max_memory_mb is not None and memory_upper_mb > budget.max_memory_mb:
        return False, "Hard request memory limit would be exceeded"
    if budget.max_estimated_compute_ms is not None:
        if estimated_compute_ms is None:
            return (
                False,
                "Unknown compute estimate under a hard estimated-compute budget",
            )
        if estimated_compute_ms > budget.max_estimated_compute_ms:
            return False, "Estimated compute budget exceeded"
    return (
        True,
        "Within declared resource limits; latency remains a target, not a guarantee",
    )
