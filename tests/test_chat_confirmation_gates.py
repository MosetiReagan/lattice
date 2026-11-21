"""Synthetic analysis records: not model, performance or hardware evidence."""

import importlib.util
import json
from pathlib import Path

import pytest

from lattice.config import file_hash


@pytest.fixture
def prepared_analysis(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "chat_gate_analysis", scripts / "analyze_chat_admission.py"
    )
    analysis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analysis)
    monkeypatch.setattr(analysis, "ROOT", tmp_path)
    # The analyzer records its statistical helper provenance as well.
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/analyze_admission_confirmation.py").write_text("fixture")
    (tmp_path / "docs").mkdir()
    workloads = tmp_path / "benchmarks/workloads"
    workloads.mkdir(parents=True)
    root = tmp_path / "benchmarks/results/chat-burst-confirmation-v1"
    root.mkdir(parents=True)
    arms = ["native4", "lattice_coalesce2"]
    settings = {
        arm: {
            "native_slots": 4 if arm == "native4" else 2,
            "batch_tokens": 256,
            "ubatch_tokens": 256,
        }
        for arm in arms
    }
    identity = {
        "runner_sha256": "runner",
        "transport_runner_sha256": "transport",
        "model_sha256": "model",
        "backend_sha256": "backend",
    }
    protocol = {
        "candidate": arms[1],
        "baselines": arms[:1],
        "arm_settings": settings,
        "sessions": [{"seed": seed, "traces": 1} for seed in range(3)],
        "source_sha256": "source",
        **identity,
        "threads": 4,
        "context_per_request": 2048,
        "worker_address_space_mb": 4096,
        "latency_ratio_max": 0.8,
        "throughput_ratio_min": 0.95,
        "host_cpu_steal_max": 0.05,
        "host_cpu_interval_steal_max": 0.1,
    }
    protocol_path = workloads / "chat-burst-confirmation-v1.json"
    protocol_path.write_text(json.dumps(protocol))
    (root / "orchestration.json").write_text(
        json.dumps({"status": "completed", "protocol_sha256": file_hash(protocol_path)})
    )
    for index, seed in enumerate(range(3), 1):
        folder = root / f"session-{index}"
        folder.mkdir()
        trace = [
            {
                "id": kind,
                "class": kind,
                "prompt_sha256": kind,
                "arrival_seconds": 0.0,
                "max_tokens": 1,
            }
            for kind in ("interactive", "bulk")
        ]
        manifest = {
            "seed": seed,
            "trace_count": 1,
            "arms": arms,
            "traces": [trace],
            "source": {"sha256": "source"},
            **identity,
            "threads": 4,
            "context_per_request": 2048,
            "worker_address_space_mb": 4096,
        }
        (folder / "manifest.json").write_text(json.dumps(manifest))
        records = []
        for arm in arms:
            records.append(
                {
                    "arm": arm,
                    "trace": 0,
                    **settings[arm],
                    "makespan_seconds": 1.0,
                    "worker_rss_peak_bytes": 1024,
                    "control_plane_rss_peak_bytes": 1024,
                    "worker_swap_peak_bytes": 0,
                    "host_cpu": {
                        "available": True,
                        "aggregate_steal_fraction": 0.01,
                        "max_interval_steal_fraction": 0.01,
                    },
                    "rows": [
                        {
                            **row,
                            "status": "completed",
                            "completion_tokens": 1,
                            "prompt_tokens": 3,
                            "token_ids": [7],
                            "text": "gold",
                            "exact_correct": True,
                            "latency_ms": 100 if arm == "native4" else 50,
                            "dispatch_lateness_ms": 0,
                        }
                        for row in trace
                    ],
                }
            )
        (folder / "results.jsonl").write_text(
            "\n".join(json.dumps(record) for record in records) + "\n"
        )
    return analysis, root


@pytest.mark.parametrize("failure", [None, "host", "output"])
def test_complete_gate_cannot_hide_cpu_or_output_failures(prepared_analysis, failure):
    analysis, root = prepared_analysis
    path = root / "session-1/results.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    if failure == "host":
        records[1]["host_cpu"]["aggregate_steal_fraction"] = 0.75
    if failure == "output":
        records[1]["rows"][0]["token_ids"] = [8]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    analysis.main()
    report = json.loads((root / "analysis.json").read_text())
    assert report["restricted_gate_pass"] is (failure is None)
    assert report["gates"]["host_cpu_eligibility"] is (failure != "host")
    assert report["gates"]["quality_and_errors"] is (failure != "output")
    assert report["gates"]["latency"] and report["gates"]["throughput"]


def test_second_native_throughput_challenger_is_not_ignored(prepared_analysis):
    analysis, root = prepared_analysis
    protocol_path = (
        analysis.ROOT / "benchmarks/workloads/chat-burst-confirmation-v1.json"
    )
    protocol = json.loads(protocol_path.read_text())
    protocol["baselines"].append("native8")
    protocol["gate_baselines"] = ["native4", "native8"]
    protocol["arm_settings"]["native8"] = {
        **protocol["arm_settings"]["native4"],
        "native_slots": 8,
    }
    protocol_path.write_text(json.dumps(protocol))
    (root / "orchestration.json").write_text(
        json.dumps({"status": "completed", "protocol_sha256": file_hash(protocol_path)})
    )
    for index in range(1, 4):
        folder = root / f"session-{index}"
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["arms"].insert(1, "native8")
        manifest_path.write_text(json.dumps(manifest))
        path = folder / "results.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines()]
        challenger = {
            **records[0],
            "arm": "native8",
            "native_slots": 8,
            "makespan_seconds": 0.5,
        }
        records.insert(1, challenger)
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    analysis.main()
    report = json.loads((root / "analysis.json").read_text())
    assert report["comparisons"]["native4"]["point_estimates"]["throughput_ratio"] == 1
    assert report["gates"]["quality_and_errors"]
    assert not report["gates"]["throughput"]
    assert not report["restricted_gate_pass"]
