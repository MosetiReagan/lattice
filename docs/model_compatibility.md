# Candidate model and backend compatibility

Phase A candidate matrix, updated with Phase B evidence: Qwen2.5 0.5B official FP16 GGUF is now tested with the pinned llama.cpp CPU adapter; see `baseline_runtime.md`. Qwen 1.5B, SmolLM, alternate precisions and all other backends remain untested. The candidate table below is research metadata, not a blanket compatibility certification. Model metadata/config snapshots were retrieved on 2026-11-19. Re-fetch config/tokenizer at immutable metadata revisions before provisioning; current snapshots used `main` and are research evidence, not a benchmark artifact lock.

| Candidate / original checkpoint | Architecture / exact parameters | Original format / tokenizer | Config context | License / role |
|---|---|---|---|---|
| [Qwen/Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) | Qwen2ForCausalLM; 494,032,768 | BF16 safetensors; Qwen2 BPE, vocabulary 151,936 | 32,768 | Apache-2.0; first baseline and potential draft |
| [Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) | Qwen2ForCausalLM; 1,543,714,304 | BF16 safetensors; Qwen2 BPE, vocabulary 151,936 | 32,768 | Apache-2.0; target after memory probe |
| [HuggingFaceTB/SmolLM2-135M-Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct) | LlamaForCausalLM; 134,515,008 | BF16 safetensors; model-specific tokenizer, vocabulary 49,152 | 8,192 | Apache-2.0; optional cheap smoke test outside target size range |

Revisions from API metadata:

- Qwen 0.5B: `7ae557604adf67be50417f59c2c2f167def9a775`.
- Qwen 1.5B: `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`.
- SmolLM2 135M: `12fd25f77366fa6b3b4b768ec3050bf629380bac`.

First two models are the core test set; third is optional. Matching Qwen vocabulary size does not prove tokenizer equivalence: compare token→ID mappings, special tokens, BOS/EOS handling, chat templates and logits shape before speculation. SmolLM is not a Qwen draft. Verify chat template from original tokenizer assets. Config context is not a tested or promised context; first runs cap total context at 2,048 tokens.

| Backend | Candidate architecture path | Attention | Weight/precision candidate | Lattice status |
|---|---|---|---|---|
| llama.cpp CPU | Qwen2 and Llama conversion to GGUF | Native CPU attention, not PyTorch SDPA | F16 GGUF first; Q8_0 / Q4_K_M later | Proposed; conversion, tokenization, serving and KV-type compatibility must be tested |
| Transformers CPU | Original Qwen2 / Llama classes | Eager/SDPA where supported | FP32/BF16/FP16 subject to CPU operator support; no automatic dtype speed claim | Reference candidate, not installed |
| vLLM | Qwen2 / Llama upstream families | Device-specific engine attention | Quantized formats depend on device/model/kernel | Deferred, not installed/tested |
| SGLang | Qwen2 / Llama upstream families | Device-specific engine attention | Quantized formats depend on platform/version | Deferred, not installed/tested |

F16 GGUF conversion from original BF16 is a derived representation and must have its own hash and converter commit; benchmark the exact same F16 file for baseline versus cache/speculation/controller tests. Quantization comparisons deliberately change representation and must be labeled separately.

## Precision capability planning matrix

| Representation | llama.cpp | Transformers ecosystem | vLLM / SGLang |
|---|---|---|---|
| FP32 / FP16 / BF16 | GGUF/build/operator-dependent, F16 baseline planned | Device/dtype-dependent | Device/dtype-dependent |
| GGUF Q8_0 / Q4_K_M | Primary low-bit candidates | Not a general native execution format; import/conversion differs | Specific GGUF support varies; do not assume parity |
| GPTQ / AWQ | No planned direct loading; conversion is a separate artifact | Requires supported loader and kernels | Specific architecture/device/kernel combinations only |
| bitsandbytes INT8 / NF4 / FP4 | Not interchangeable with GGUF | Supported operation/device combinations only | Backend/version support must be probed |
| Quantized KV | Backend cache types separate from weights | Cache implementation/device dependent | Backend/device dependent |

Only the Qwen 0.5B FP16 GGUF/CPU path has now been tested; every other precision combination is untested. INT4 is a bit width, not an interchangeable layout. Group size, calibration data, excluded tensors and runtime kernels belong in the manifest. Measure load time, peak memory, prefill/decode, perplexity and task quality per artifact; smallest artifact does not become default automatically.

## Deferred model families

Llama, Gemma and Granite are candidates for later architecture/license review, not supported models. Llama and Gemma use model-specific terms that must not be called generally permissive; Granite and SmolLM licenses also require exact checkpoint verification. Qwen family licenses vary across checkpoints (do not extrapolate these two Apache model cards to every Qwen). 3B–4B tests require an explicit memory/storage plan. No third-party weight ownership is claimed.
