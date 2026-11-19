"""Export only measured summaries, never placeholder production metrics."""

import datetime
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = []
for name in ["standard-session-1", "standard-session-2", "standard-session-3"]:
    path = root / "benchmarks/results" / name / "summary.json"
    if path.exists():
        for workload, item in json.loads(path.read_text())["workloads"].items():
            rows.append(
                {
                    "group": "Standard baseline",
                    "label": name + " / " + workload,
                    "latency_ms": item["latency_ms"]["median"],
                    "rss_mib": None
                    if item["sampled_worker_rss_bytes"]["median"] is None
                    else item["sampled_worker_rss_bytes"]["median"] / 1024**2,
                    "tokens_per_second": item["aggregate_generated_tokens_per_second"],
                    "samples": item["completed"],
                    "failed": item["failed"],
                    "quality": None,
                    "source": str(path.relative_to(root)),
                }
            )
for name in ["cache-session-1", "cache-session-2", "cache-session-3"]:
    path = root / "benchmarks/results" / name / "summary.json"
    if path.exists():
        for workload, arms in json.loads(path.read_text()).items():
            for arm, item in arms.items():
                rows.append(
                    {
                        "group": "Warmed prefix ablation",
                        "label": name + " / " + workload + " / " + arm,
                        "latency_ms": item["latency_ms"]["median"],
                        "rss_mib": None,
                        "tokens_per_second": None,
                        "samples": item["latency_ms"]["n"],
                        "failed": 0,
                        "quality": "Exact token equality checked per pair",
                        "source": str(path.relative_to(root)),
                    }
                )
path = root / "benchmarks/results/precision-session-1/summary.json"
if path.exists():
    for model, item in json.loads(path.read_text()).items():
        rows.append(
            {
                "group": "Precision quality",
                "label": model,
                "latency_ms": None,
                "rss_mib": None,
                "tokens_per_second": None,
                "samples": item["smoke_tasks"],
                "failed": None,
                "quality": f"Smoke {item['smoke_passed']}/{item['smoke_tasks']}; WikiText subset PPL {item['perplexity']:.4f}",
                "source": str(path.relative_to(root)),
            }
        )
path = root / "benchmarks/results/speculative-session-1/summary.json"
if path.exists():
    data = json.loads(path.read_text())
    for length in ["1", "2", "4", "8"]:
        for arm, item in data[length].items():
            rows.append(
                {
                    "group": "Native greedy speculation",
                    "label": f"draft {length} / {arm}",
                    "latency_ms": item["latency_ms"]["median"],
                    "rss_mib": item["rss_bytes"]["median"] / 1024**2,
                    "tokens_per_second": None,
                    "samples": item["latency_ms"]["n"],
                    "failed": 0,
                    "quality": f"{len(data['greedy_mismatches'])} greedy mismatches across paired outputs",
                    "source": str(path.relative_to(root)),
                }
            )
path = root / "benchmarks/results/adaptive-session-1/summary.json"
if path.exists():
    for workload, arms in json.loads(path.read_text()).items():
        for arm, item in arms.items():
            rows.append(
                {
                    "group": "Integrated adaptive evaluation",
                    "label": workload + " / " + arm,
                    "latency_ms": item["latency_ms"]["median"],
                    "rss_mib": None,
                    "tokens_per_second": None,
                    "samples": item["latency_ms"]["n"],
                    "failed": 0,
                    "quality": "Exact known-prompt greedy equality checked",
                    "source": str(path.relative_to(root)),
                }
            )
result = {
    "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    "rows": rows,
    "notice": "Measured CPU development experiments. No cross-workload aggregate or production performance guarantee. Empty cells are unavailable.",
}
(root / "dashboard/data.json").write_text(json.dumps(result, indent=2) + "\n")
