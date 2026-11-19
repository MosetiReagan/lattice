# Lattice Phase A: research and feasibility

Status: proposed design, awaiting Phase A review. Researched 2026-11-19 using public primary sources. No model inference, performance measurements, or hardware compatibility certification has been performed. Source snapshots and retrieval timestamps/hashes are in `evidence/sources.json`; upstream claims are not Lattice results. README snapshots track moving branches and may differ from release tags below. Broken source URLs are retained as failures; ONNX documentation was used instead of its unavailable README.

## Environment audit

| Item | Observed |
|---|---|
| Host | Linux 6.18.60-instabox, x86-64 VM |
| CPU | 4 exposed AMD EPYC vCPUs, AVX2 and AVX-512 advertised |
| RAM | 7.8 GiB total; approximately 7.2 GiB available at inspection |
| Swap | 4 GiB; swapping invalidates performance comparisons |
| Disk | 20 GiB volume, approximately 15 GiB free at inspection |
| Python | python3 3.13.5; unqualified python absent |
| Build tools | GCC/G++ available; CMake absent |
| GPU | No NVIDIA device nodes, nvidia-smi, nvcc, or /dev/dri found |
| Frameworks | PyTorch, Transformers, vLLM, SGLang, llama-cpp-python, ONNX Runtime, bitsandbytes, huggingface-hub not installed |
| Resource limits | Conventional cgroup-v2 cpu.max/memory.max paths unavailable; do not infer unlimited resources |
| Repository | Workspace initially empty; public GitHub lookup for mosetireagan/lattice returned 404 (private or absent unresolved) |

CUDA and PyTorch versions cannot be reported: neither is installed/detected. No GPU, MPS, or backend has been tested. Shared VM scheduling and advertised ISA support need validation under load. Work stays in `/data/workspace/lattice`; no remote was modified.

## Backend decision

Choose **llama.cpp**, initially a CPU `llama-server` subprocess with one loaded GGUF model, plus `llama-bench`/perplexity utilities as appropriate. Reasons: native CPU execution, small deployment footprint, Qwen2 architecture support, F16 and GGUF quantized execution, streaming, timings, and existing cache/batching facilities. Retain upstream attribution. Do not claim that controlling its flags implements a new decoding algorithm.

Use the latest-release lookup only as discovery: llama.cpp `v1.0.0`, published 2026-11-13, API target commit `2d8a32502909ca065c41c4cf5f2fb1c427c047fc`; vLLM `v0.34.0`, published 2026-11-16; SGLang `v0.5.23`, published 2026-11-02. Resolve and record actual checkout commits, binary hashes, licenses and build flags before Phase B. Neither a release API response nor a README establishes tested compatibility. Reconcile moving-branch documentation against the pinned binary's `--help`.

Transformers is the secondary correctness/reference backend when dependency and disk budgets permit, not an extra prerequisite for the first request. vLLM and SGLang are later GPU/high-concurrency candidates; both advertise CPU and other accelerator support, so they are not categorically GPU-only. Their platform-specific installation and memory overhead must be evaluated rather than assumed suitable for this 8 GiB VM.

## Mandatory technology audit

Complexity below describes integration/validation effort, not a benchmark. H=high, M=medium, L=low.

| Technology / source | Purpose and problem solved | Hardware / complexity | Trade-offs and existing capability | Additional Lattice contribution |
|---|---|---|---|---|
| [llama.cpp](https://github.com/ggml-org/llama.cpp), MIT | Local autoregressive serving, GGUF, CPU efficiency | CPU; optional CUDA/Metal/etc.; M | Already speculative decoding, prompt reuse, KV types, continuous batching; native APIs and flags evolve | Admission, measured path policy, safe prefix identity, experiment provenance |
| [vLLM](https://github.com/vllm-project/vllm), Apache-2.0 | High-throughput serving and KV memory management | Platform-specific CPU/GPU builds; H | PagedAttention, continuous batching, prefix caching, quantization, speculative methods already exist; throughput/latency and residency trade-offs | Cross-strategy quality-cost decisions, workload evidence; reuse scheduler |
| [SGLang](https://github.com/sgl-project/sglang), Apache-2.0 | Structured/agent serving and prefix reuse | Multiple accelerator/CPU paths; H | RadixAttention and speculative/quantized serving ecosystem; version/model-specific constraints | Cache-aware admission/routing and reproducible policy evaluation |
| [Transformers](https://github.com/huggingface/transformers), Apache-2.0 | Broad architectures and reference generation | PyTorch CPU/CUDA/MPS depending on model; M | Assisted generation, cache classes, SDPA integration already exist; flexible but runtime overhead | Probability-level reference, independent sampling tests, capability probes |
| [TGI](https://github.com/huggingface/text-generation-inference) | Production streaming, batching, quantized serving | GPU-oriented, CPU fallback documented; H | README states maintenance mode; includes speculation and continuous batching; inspect pinned license (historical licensing changed) | Comparison only; avoid new primary dependency |
| [TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM), Apache-2.0 | Compiled NVIDIA serving optimizations | Supported NVIDIA/CUDA stack, version-specific; H | Strong specialization and build/engine constraints; already batching/cache/speculation | Future adapter and build provenance, no custom engine compiler |
| [ONNX Runtime](https://onnxruntime.ai/docs/), MIT | Portable graph execution using execution providers | CPU/CUDA/DirectML/etc. provider-specific; H | Export, generation integration and operator coverage cost; quantization support not universal | Future capability-gated execution, not initial backend |
| [bitsandbytes](https://github.com/bitsandbytes-foundation/bitsandbytes), MIT | Low-bit linear operations and weight loading | Platform/operation-specific CPU and accelerator matrix; M-H | LLM.int8, NF4/FP4; reduced storage is not guaranteed speed or quality preservation | Measured format selection; no assumption of universal CUDA-only or CPU parity |
| [GPTQ](https://github.com/IST-DASLab/gptq), Apache-2.0 | Calibration-based post-training weight quantization | Calibration memory plus compatible low-bit kernels, often CUDA; H | Group sizes, calibration and kernel availability change quality/speed | Artifact/calibration manifest and quality acceptance |
| [AWQ](https://github.com/mit-han-lab/llm-awq), MIT | Activation-aware weight quantization | Calibration and supported kernels, commonly GPU; H | Protects salient weights; runtime-specific layouts, no blanket INT4 compatibility | Evidence-backed variant selection |
| [FlashAttention](https://github.com/Dao-AILab/flash-attention), BSD-3-Clause | IO-efficient exact attention | Version-specific CUDA/ROCm GPUs; H | FA2 CUDA documents Ampere/Ada/Hopper and CUDA >=12; FA3 has Hopper constraints; not CPU attention | Capability detection and measured prefill break-even; reuse kernels |
| [PyTorch SDPA](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html), PyTorch BSD-style | Attention dispatch to math/fused kernels | CPU math or eligible accelerators; L-M | Backend dispatch depends on dtype, shapes, mask/device; numerical differences possible | Record actual dispatch and test output tolerance |

Licenses above are planning metadata, not a dependency lock or redistribution clearance. Validate exact shipped versions and transitive notices.

## Research mechanisms and boundaries

| Mechanism / primary reading | Existing implementation, requirements and trade-off | Lattice experiment / complexity |
|---|---|---|
| [Speculative sampling, Leviathan et al.](https://arxiv.org/abs/2211.17192) | Draft plus parallel target verification; available in mature engines; extra model memory and draft overhead can outweigh saved target passes | Draft-length break-even and acceptance feedback; H. Need full proposal/target distributions for exact stochastic correction |
| [Multi-token prediction](https://arxiv.org/abs/2404.19737) | Requires compatible trained prediction heads; not a generic switch on arbitrary checkpoints | Defer training; capability-gated adapter, H |
| [H2O KV eviction](https://arxiv.org/abs/2306.14048), [KIVI](https://arxiv.org/abs/2402.02750) | Compression/eviction reduces memory but can alter quality; low-bit KV needs kernels and layouts | Compare backend KV types first; context eviction is approximate and opt-in, H |
| [PagedAttention](https://arxiv.org/abs/2309.06180) | vLLM block-managed KV allocation; allocator complexity and concurrency benefits | Delegate physical pages; own accounting/reservation policies, M |
| [RadixAttention](https://arxiv.org/abs/2312.07104) | SGLang prefix-tree reuse; llama.cpp also prompt reuse; requires identical compatible prefix | Tenant-scoped cache namespace and eviction-value policy, M |
| [Orca continuous batching](https://www.usenix.org/conference/osdi22/presentation/yu) | Iteration scheduling admits requests between decode steps; engines already implement it | Bounded admission, fairness and deadlines outside backend; do not duplicate token scheduler, M |
| Dynamic batching | Accumulate compatible work before execution; queue delay can hurt TTFT | Sweep queue delay against throughput; delegate batching, M |
| [CALM adaptive computation](https://arxiv.org/abs/2207.07061) / early exiting | Needs architecture/training and calibrated exit criteria; confidence is not correctness | Defer early exits; research only, H |
| [FrugalGPT cascades](https://arxiv.org/abs/2305.05176) | Multiple model calls, learned selection; costs and task suitability need labels | Deterministic task-stratified routing only after held-out evidence, M-H |
| Token confidence | Entropy/max probability depends on calibration and tokenizer; unreliable complexity proxy | Track confidence separately from verified task quality; no semantic-understanding claim, M |
| Quantization (GPTQ/AWQ above) | Weight compression versus quality/kernel overhead; backend-specific | F16 vs Q8_0 vs Q4_K_M converted from same checkpoint, M |
| [Energy-aware inference](https://arxiv.org/abs/2311.16863) | Device telemetry/power meter needed; latency and memory are not energy | Record joules only with attributable measurement; unavailable on this VM, H |

Exact stochastic speculative sampling uses acceptance min(1,p(x)/q(x)); on rejection sample normalized max(p-q,0), and on full acceptance draw a bonus token from the target. p and q must include the same declared sampling transformations and correct history. Handle q=0 and numerical residuals; roll back target/draft caches. The initial optimization experiment is greedy only. Top-p/top-k/temperature/penalties remain unsupported for stochastic speculation until full-distribution instrumentation and statistical tests exist. A top-N logprob endpoint is insufficient. Fall back explicitly, preserving requested settings. A backend speculative endpoint does not alone prove distribution preservation.

## Lattice-specific research hypotheses

1. A measured, interpretable controller can avoid negative-benefit speculation and select a cheaper compatible path subject to quality tolerances.
2. Explicit tenant-safe prefix reservation and value-based eviction may improve repeated-prefix workloads at fixed memory limits.
3. Quality-qualified precision/model routing may reduce resource use for known request classes; evaluate routing error and fallback costs, not parameter count.
4. Bounded admission may improve tail latency under overload without modifying backend kernels.

These are hypotheses, not established novelty or results. A literature/patent novelty claim is outside this feasibility study. Baselines include backend defaults and tuned backend configurations, so Lattice is compared against competent use of existing engines.

## License recommendation

Recommend Apache-2.0 for original Lattice code: permissive redistribution with an explicit contributor patent grant and preservation of notices. MIT is simpler but lacks the same explicit patent terms; BSD-3-Clause is also permissive. Apache-2.0 does not relicense model weights or third-party code. Adopt LICENSE and NOTICE during implementation after confirming ownership and dependency inventory. No license file is adopted by this study alone.

## Feasibility verdict

A CPU Qwen 0.5B F16 baseline is plausible here; 1.5B is a follow-up with measured memory admission. Performance gains, exact decoding equivalence, 3–4B feasibility, accelerator support and release acceptance remain unproven. Proceed only to the small baseline milestone after Phase A review; see architecture, compatibility, benchmark methodology and roadmap.
