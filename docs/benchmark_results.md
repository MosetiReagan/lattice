# Current evidence and benchmark status

Phase B has executed real model smoke/integration tests, **not controlled inference benchmarks**. No latency improvement, throughput gain, memory saving, energy benefit or quality preservation claim is supported yet. The single-request observations in `artifacts/first-generation.json` establish functioning instrumentation, not repeatability or an optimization comparison.

| Configuration | Latency | Throughput | Memory | Quality |
|---|---|---|---|---|
| Standard baseline | Smoke timing recorded; repeated benchmark unavailable | Repeated benchmark unavailable | Unavailable | Unavailable |
| Speculative decoding | Unavailable | Unavailable | Unavailable | Unavailable |
| Quantized inference | Unavailable | Unavailable | Unavailable | Unavailable |
| KV-cache optimized | Unavailable | Unavailable | Unavailable | Unavailable |
| Adaptive execution | Unavailable | Unavailable | Unavailable | Unavailable |

Resource projections in `roadmap.md` remain estimates. See `benchmark_methodology.md` for planned controls and sample requirements. The frozen baseline, quality data and eight workload categories remain Phase C work.

## Release gate status

| Gate | Status |
|---|---|
| G1 real model runtime | Met for the baseline: real official Qwen 0.5B FP16 artifact generates valid bounded tokens |
| G2 tested backend | Met for the documented narrow CPU scope: pinned llama.cpp load/generate/stream/cancel/reload tested; no accelerator certification |
| G3 reproducible baseline | Not met: working provisioning and smoke commands, but repeated frozen workload measurements pending |
| G4 three independent optimizations | Not met: none implemented |
| G5 measured adaptive execution | Not met: design only |
| G6 quality preservation | Not met: no controlled quality evaluation |
| G7 repeatable improvement | Not met: no optimization performance experiments |
| G8 stability | Partial: queue, timeout, cancellation, HTTP disconnect, recovery and failure tests pass; broader concurrency/resource hardening pending |
| G9 documentation | Partial: research, architecture, working baseline, security, profiling and limitations documented; optimization documentation awaits implementation |
| G10 reproducibility | Partial: exact model revision/hash, source commit, build metadata, Python lock and reproduction scripts present; published full benchmarks pending |

Test evidence: 20 mocked/control-plane checks and six real CPU/integration checks (including live HTTP), 26 passing in the initial combined run. `artifacts/all-tests.txt` contains the latest full run. Mocks are not hardware evidence. No GPU tests ran.

Classification: unreleased `0.1.0.dev0` baseline development build. Not Lattice 1.0; G3–G10 remain incomplete.
