# Tested hardware and backend scope

| Environment | Status |
|---|---|
| This Linux x86-64 VM, AMD EPYC, 4 exposed cores, 7.8 GiB RAM | Tested real generation, streaming, cancellation/reload and API with the pinned llama.cpp build and Qwen FP16 artifact |
| Other Linux CPU hosts | Candidate; rebuild native binary and rerun integration tests |
| NVIDIA/CUDA | Untested; no GPU detected; never inferred from a mock |
| Apple Silicon/MPS/Metal | Untested; current process/resource implementation is Linux-specific |
| AMD/Intel GPUs and other accelerators | Untested |
| Transformers/vLLM/SGLang adapters | Not implemented |

The worker explicitly disables GPU layers and uses F16 KV. Upstream backend platform support is not equivalent to Lattice hardware support. Do not reuse the native-ISA binary on other processors. Installation and verification commands are in baseline_runtime.md. No automatic accelerator capability selector is implemented yet.

The repository now contains separate unit and manually requested real-CPU GitHub Actions jobs. They have not run remotely in this session and are not evidence of additional hardware support. Fresh backend builds have different hashes or CPU/thread fingerprints and must not inherit this VM's adaptive evidence automatically; integration tests accept the safe standard fallback until local experiments qualify that build.

Current evidence also includes real Q8_0/Q4_K_M 0.5B CPU runs and the official 1.5B Q8 target with 0.5B FP16 draft. CPU capability/thread fingerprints bind adaptive profiles to this measured scope. No claim extends these results to other CPU models, accelerator kernels or runtime versions without rerunning compatibility and quality checks.

The opt-in two-slot mode is now tested on this same CPU with Qwen2.5 0.5B FP16. Startup checks the native slot count, per-slot context and private stream cancellation controls. Three mixed-length sessions retain sampled worker VmSwap=0 and report short/long/makespan trade-offs; no other concurrent model/precision/hardware combination is certified by that evidence.

A separate [8k-context retrieval check](long_context_dataset_results.md) tested explicit Qwen 0.5B FP16 standard execution on this CPU with 8,192 context tokens, 60 frozen synthetic retrieval prompts and a 32-token output cap. All 60 completed without input truncation; measured prompt lengths reached 5,874 tokens. This is a narrow functional/quality observation, not certification of all 8k workloads, model variants, memory performance or accelerators.
