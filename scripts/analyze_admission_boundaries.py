"""Report every boundary diagnostic, including regressions and empty classes."""

import json
from pathlib import Path

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def p95(values):
    if not values:
        return None
    ordered = sorted(values)
    index = 0.95 * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def summarize(result):
    rows = result["rows"]
    completed = [row for row in rows if row["status"] == "completed"]
    if any(row["completion_tokens"] != len(row["token_ids"]) for row in completed):
        raise ValueError("Output token accounting mismatch")
    if any(row["completion_tokens"] > row["max_tokens"] for row in completed):
        raise ValueError("Output cap violated")
    return {
        "interactive_p95_ms": p95(
            [row["latency_ms"] for row in completed if row["class"] == "interactive"]
        ),
        "bulk_p95_ms": p95(
            [row["latency_ms"] for row in completed if row["class"] == "bulk"]
        ),
        "tokens_per_second": sum(row["completion_tokens"] for row in completed)
        / result["makespan_seconds"],
        "errors": len(rows) - len(completed),
        "exact_correct": sum(row["exact_correct"] for row in completed),
        "requests": len(rows),
        "worker_rss_peak_bytes": result["worker_rss_peak_bytes"],
        "worker_swap_peak_bytes": result["worker_swap_peak_bytes"],
    }


def compare_outputs(reference, candidate):
    left = {row["id"]: row for row in reference["rows"]}
    right = {row["id"]: row for row in candidate["rows"]}
    if left.keys() != right.keys():
        raise ValueError("Request IDs differ")
    return [
        key
        for key in left
        if any(
            left[key].get(field) != right[key].get(field)
            for field in (
                "status",
                "prompt_sha256",
                "arrival_seconds",
                "max_tokens",
                "prompt_tokens",
                "token_ids",
                "text",
            )
        )
    ]


def main():
    root = ROOT / "benchmarks/results/burst-coalescing-boundaries-v1"
    results_path = root / "results.jsonl"
    results = json.loads((root / "summary.json").read_text())
    if results != [json.loads(line) for line in results_path.read_text().splitlines()]:
        raise ValueError("Boundary summary differs from raw results")
    if len(results) != 13:
        raise ValueError("Incomplete boundary matrix")
    groups = {}
    for result in results:
        group = groups.setdefault(result["case"], {})
        if result["arm"] in group:
            raise ValueError("Duplicate case/arm")
        group[result["arm"]] = result
    report = {"results_sha256": file_hash(results_path), "cases": {}}
    lines = [
        "# Admission boundary diagnostics",
        "",
        "These are single-trace diagnostics fixed before confirmation completed. They do not replace the frozen primary gate, support confidence intervals, or establish production generalization. No cases are dropped and no policy is retuned from them.",
        "",
        "All arms use the same CPU, Qwen2.5 0.5B FP16, greedy sampling, four threads, batch/microbatch256, per-request context2048 and 4096 MiB worker address-space limit. Empty request classes have unavailable P95, not zero latency.",
        "",
        "| Case | Arm | Interactive P95 ms | Bulk P95 ms | Actual tokens/s | Errors | Exact task correct | Worker MiB |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case, arms in groups.items():
        reference = arms.get("native8", arms.get("native16"))
        if reference is None:
            raise ValueError("Missing native reference")
        values = {}
        for arm, result in arms.items():
            value = summarize(result)
            value["output_mismatch_ids"] = compare_outputs(reference, result)
            values[arm] = value
            interactive = value["interactive_p95_ms"]
            bulk = value["bulk_p95_ms"]
            lines.append(
                f"| {case} | {arm} | "
                + (f"{interactive:.1f}" if interactive is not None else "Unavailable")
                + " | "
                + (f"{bulk:.1f}" if bulk is not None else "Unavailable")
                + f" | {value['tokens_per_second']:.2f} | {value['errors']} | {value['exact_correct']}/{value['requests']} | {value['worker_rss_peak_bytes'] / 1024**2:.1f} |"
            )
        report["cases"][case] = values
    mismatch_count = sum(
        len(value["output_mismatch_ids"])
        for arms in report["cases"].values()
        for value in arms.values()
    )
    lines += [
        "",
        f"Output/input/arrival mismatch count against each case's native reference: **{mismatch_count}**. Exact task correctness is separate from baseline-output preservation.",
        "",
        "The native16/native32 challengers use development seed1002 and are diagnostic only. They extend the finite native slot sweep; they are not additional held-out confirmation sessions. Control-plane RSS in the raw files belongs to the common benchmark harness and is not isolated gateway memory.",
        "The native32 arm returned five generation errors; its private backend diagnostic log reports std::bad_alloc under the fixed address-space cap. It is not a successful compatible baseline under this configuration. Its partial throughput is retained, not treated as a competitive target.",
        "",
        "The opt-in 50 ms delay explicitly trades bulk admission latency for burst coalescing. Interactive-only, bulk-only, late-arrival and altered-mix outcomes must all inform deployment suitability. None changes the frozen confirmation decision.",
        "",
    ]
    (root / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "docs/admission_boundaries.md").write_text("\n".join(lines))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
