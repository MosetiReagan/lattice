import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "admission_analysis",
    Path(__file__).resolve().parents[1] / "scripts/analyze_admission_confirmation.py",
)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)
BOUNDARY_SPEC = importlib.util.spec_from_file_location(
    "admission_boundaries_analysis",
    Path(__file__).resolve().parents[1] / "scripts/analyze_admission_boundaries.py",
)
boundary = importlib.util.module_from_spec(BOUNDARY_SPEC)
BOUNDARY_SPEC.loader.exec_module(boundary)


def trace(latency, seconds=10):
    return {
        "interactive_ms": [latency] * 6,
        "bulk_ms": [200.0] * 6,
        "tokens": 120,
        "seconds": seconds,
        "errors": 0,
    }


def test_interpolated_p95_uses_full_distribution():
    assert analysis.percentile([0, 10], 0.95) == pytest.approx(9.5)
    assert analysis.percentile([10], 0.95) == 10
    with pytest.raises(ValueError):
        analysis.percentile([], 0.95)


def test_paired_ratio_and_real_makespan_throughput():
    pairs = [{"native8": trace(100, 10), "candidate": trace(70, 11)} for _ in range(3)]
    metrics = analysis.metrics(pairs, "native8")
    assert metrics["p95_ratio"] == 0.7
    assert metrics["throughput_ratio"] == pytest.approx(10 / 11)
    assert metrics["baseline_tokens_per_second"] == 12


def test_hierarchical_resampling_retains_whole_paired_traces():
    pair = {"native8": trace(100), "candidate": trace(70)}
    result = analysis.bootstrap(
        [[pair] * 2 for _ in range(3)], "native8", replicates=100
    )
    assert result["p95_ratio_95_interval"] == pytest.approx([0.7, 0.7])
    assert result["throughput_ratio_95_interval"] == [1.0, 1.0]


def test_throughput_loss_not_hidden_by_latency_win():
    pair = {"native8": trace(100), "candidate": trace(1, 12)}
    result = analysis.bootstrap(
        [[pair] * 2 for _ in range(3)], "native8", replicates=100
    )
    assert result["p95_ratio_95_interval"][1] <= 0.8
    assert result["throughput_ratio_95_interval"][0] < 0.95


def test_empty_traffic_class_is_unavailable_not_zero_latency():
    assert boundary.p95([]) is None


def test_boundary_comparison_detects_arrival_and_output_changes():
    reference = {"rows": [{"id": "a", "arrival_seconds": 0.03, "text": "same"}]}
    shifted = {"rows": [{"id": "a", "arrival_seconds": 0.04, "text": "same"}]}
    assert boundary.compare_outputs(reference, shifted) == ["a"]
    with pytest.raises(ValueError, match="Request IDs differ"):
        boundary.compare_outputs(reference, {"rows": []})
