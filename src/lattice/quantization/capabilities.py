"""Formats are not interchangeable just because their bit widths match."""

from dataclasses import dataclass
from enum import StrEnum


class WeightFormat(StrEnum):
    GGUF_F16 = "gguf-f16"
    GGUF_Q8 = "gguf-q8_0"
    GGUF_Q4 = "gguf-q4_k_m"
    GPTQ = "gptq"
    AWQ = "awq"
    BNB_INT8 = "bitsandbytes-int8"
    BNB_NF4 = "bitsandbytes-nf4"


@dataclass(frozen=True)
class Capability:
    executable_candidate: bool
    verified: bool
    reason: str


def capability(
    backend: str,
    device: str,
    representation: WeightFormat,
    verified_formats: frozenset[WeightFormat] = frozenset(),
) -> Capability:
    native = (
        backend == "llama.cpp"
        and device == "cpu"
        and representation
        in {WeightFormat.GGUF_F16, WeightFormat.GGUF_Q8, WeightFormat.GGUF_Q4}
    )
    return Capability(
        native,
        native and representation in verified_formats,
        "GGUF native CPU candidate; exact model/artifact must be tested"
        if native
        else "No implemented and tested Lattice execution path for this backend/device/format",
    )


@dataclass(frozen=True)
class QualityEvidence:
    source_checkpoint: str
    baseline_sha256: str
    candidate_sha256: str
    dataset_sha256: str
    relative_perplexity_change: float | None
    task_score_loss_upper_bound: float | None
    representative_held_out: bool

    def qualifies(
        self, max_relative_ppl: float = 0.02, max_task_loss: float = 0.01
    ) -> bool:
        return bool(
            self.representative_held_out
            and self.dataset_sha256
            and self.source_checkpoint
            and self.baseline_sha256 != self.candidate_sha256
            and self.relative_perplexity_change is not None
            and self.relative_perplexity_change <= max_relative_ppl
            and self.task_score_loss_upper_bound is not None
            and self.task_score_loss_upper_bound <= max_task_loss
        )
