"""Keep chat-framed boundary regressions separate from confirmation gates."""

import json
from pathlib import Path

from analyze_admission_boundaries import compare_outputs, summarize

from lattice.config import file_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "benchmarks/results/chat-admission-boundaries-v1"
    manifest = json.loads((folder / "manifest.json").read_text())
    results = json.loads((folder / "summary.json").read_text())
    raw_path = folder / "results.jsonl"
    if results != [json.loads(line) for line in raw_path.read_text().splitlines()]:
        raise ValueError("Summary does not match raw results")
    lookup = {(r["case"], r["arm"]): r for r in results}
    if len(lookup) != len(results) or len(results) != len(manifest["traces"]) * 2:
        raise ValueError("Duplicate or incomplete boundary matrix")
    arms = manifest["arms"]
    report = {"results_sha256": file_hash(raw_path), "cases": {}}
    lines = [
        "# Chat-framed admission boundaries",
        "",
        "These five single-trace diagnostics were fixed before confirmation. They do not determine tuning or replace any primary gate. Both arms use actual model chat framing, identical source inputs/arrivals, greedy sampling, caps and worker resource limits. Empty traffic classes have unavailable P95. There are no confidence intervals from these single traces.",
        "",
        "| Case | Arm | Interactive P95 ms | Bulk P95 ms | Tokens/s | Errors | Exact task correct | Worker MiB |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in manifest["traces"]:
        name = case["case"]
        expected = {row["id"]: row for row in case["requests"]}
        values = {}
        for arm in arms:
            result = lookup[name, arm]
            rows = {row["id"]: row for row in result["rows"]}
            if rows.keys() != expected.keys() or len(rows) != len(result["rows"]):
                raise ValueError("Request IDs changed")
            for key, row in rows.items():
                if any(
                    row[field] != expected[key][field]
                    for field in ("prompt_sha256", "arrival_seconds", "max_tokens")
                ):
                    raise ValueError("Input/arrival changed")
            value = summarize(result)
            value["mismatch_ids"] = compare_outputs(lookup[name, arms[0]], result)
            values[arm] = value
            interactive, bulk = value["interactive_p95_ms"], value["bulk_p95_ms"]
            lines.append(
                f"| {name} | {arm} | "
                + (f"{interactive:.1f}" if interactive is not None else "Unavailable")
                + " | "
                + (f"{bulk:.1f}" if bulk is not None else "Unavailable")
                + f" | {value['tokens_per_second']:.3f} | {value['errors']} | {value['exact_correct']}/{value['requests']} | {value['worker_rss_peak_bytes'] / 1024**2:.1f} |"
            )
        report["cases"][name] = values
    lines += [
        "",
        "All results, including regressions, failures and nonidentical outputs, are retained in the raw JSONL and analysis.json. One favorable trace is not a workload-level performance claim. Sampled worker RSS is not allocator peak; the hard worker cap is address space. Control-plane RSS is the common benchmark harness, not isolated production gateway memory.",
        "",
        "See [primary confirmation](chat_admission_confirmation.md). The candidate is opt-in and a conventional admission heuristic, not a new kernel or stronger language model.",
        "",
    ]
    (folder / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "docs/chat_admission_boundaries.md").write_text("\n".join(lines))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
