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
