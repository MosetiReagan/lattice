"""Explicit model IDs are never silently substituted by smaller models."""

from dataclasses import dataclass

from lattice.types import LatticeError


@dataclass(frozen=True)
class ModelCandidate:
    model_id: str
    task_classes: frozenset[str]
    quality_qualified: bool
    measured_latency_ms: float | None
    measured_memory_mb: float | None
    evidence_id: str | None


@dataclass(frozen=True)
class Route:
    model_id: str
    explanation: str
    evidence_id: str | None
    confidence: str


def route(
    requested: str,
    candidates: list[ModelCandidate],
    *,
    alias: str | None = None,
    task_class: str | None = None,
    profile: str = "balanced",
) -> Route:
    if alias is None:
        for candidate in candidates:
            if candidate.model_id == requested:
                return Route(
                    requested,
                    "Explicit registered model preserved",
                    candidate.evidence_id,
                    "identity constraint",
                )
        raise LatticeError("Requested model is not registered", 404, "model_not_found")
    if requested != alias or task_class is None:
        raise LatticeError(
            "Routing aliases require an explicit validated task class",
            422,
            "routing_evidence_missing",
        )
    eligible = [
        c
        for c in candidates
        if c.quality_qualified
        and task_class in c.task_classes
        and c.evidence_id
        and c.measured_latency_ms is not None
        and c.measured_memory_mb is not None
    ]
    if not eligible:
        raise LatticeError(
            "No quality-qualified measured model for this task class",
            422,
            "routing_evidence_missing",
        )
    if profile == "lowest_memory":
        chosen = min(eligible, key=lambda c: (c.measured_memory_mb, c.model_id))
    else:
        chosen = min(eligible, key=lambda c: (c.measured_latency_ms, c.model_id))
    return Route(
        chosen.model_id,
        "Minimum measured resource cost among task-qualified models",
        chosen.evidence_id,
        "held-out evidence required",
    )
