"""Fetch public primary sources; no models or executable remote code are loaded."""

import concurrent.futures
import datetime
import hashlib
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "evidence"
SOURCES = {
    "llama-readme": "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/README.md",
    "llama-server": "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md",
    "vllm-readme": "https://raw.githubusercontent.com/vllm-project/vllm/main/README.md",
    "sglang-readme": "https://raw.githubusercontent.com/sgl-project/sglang/main/README.md",
    "transformers-readme": "https://raw.githubusercontent.com/huggingface/transformers/main/README.md",
    "TGI-readme": "https://raw.githubusercontent.com/huggingface/text-generation-inference/main/README.md",
    "TensorRT-LLM-readme": "https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/main/README.md",
    "ONNX-readme": "https://raw.githubusercontent.com/microsoft/onnxruntime/main/README.md",
    "bitsandbytes-readme": "https://raw.githubusercontent.com/bitsandbytes-foundation/bitsandbytes/main/README.md",
    "GPTQ-readme": "https://raw.githubusercontent.com/IST-DASLab/gptq/main/README.md",
    "AWQ-readme": "https://raw.githubusercontent.com/mit-han-lab/llm-awq/main/README.md",
    "FlashAttention-readme": "https://raw.githubusercontent.com/Dao-AILab/flash-attention/main/README.md",
    "SDPA": "https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html",
    "speculative-paper": "https://arxiv.org/abs/2211.17192",
    "pagedattention-paper": "https://arxiv.org/abs/2309.06180",
    "radixattention-paper": "https://arxiv.org/abs/2312.07104",
    "multitoken-paper": "https://arxiv.org/abs/2404.19737",
    "h2o-paper": "https://arxiv.org/abs/2306.14048",
    "earlyexit-paper": "https://arxiv.org/abs/2207.07061",
    "frugalgpt-paper": "https://arxiv.org/abs/2305.05176",
    "energy-paper": "https://arxiv.org/abs/2311.16863",
}
for repo in [
    "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "HuggingFaceTB/SmolLM2-135M-Instruct",
]:
    name = repo.replace("/", "--")
    SOURCES[name + "-metadata"] = "https://huggingface.co/api/models/" + repo
    SOURCES[name + "-config"] = (
        "https://huggingface.co/" + repo + "/raw/main/config.json"
    )
for repo in ["ggml-org/llama.cpp", "vllm-project/vllm", "sgl-project/sglang"]:
    SOURCES[repo.replace("/", "--") + "-release"] = (
        "https://api.github.com/repos/" + repo + "/releases/latest"
    )


def fetch(item):
    name, url = item
    record = {
        "name": name,
        "url": url,
        "retrieved_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Lattice-feasibility-study"}
        )
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read()
            record.update(
                status=r.status,
                final_url=r.url,
                sha256=hashlib.sha256(body).hexdigest(),
            )
        filename = name + (
            ".json" if name.endswith(("metadata", "config", "release")) else ".txt"
        )
        (ROOT / filename).write_bytes(body)
        record["file"] = filename
    except (OSError, ValueError) as e:
        record["error"] = str(e)
    return record


ROOT.mkdir(parents=True, exist_ok=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(fetch, SOURCES.items()))
(ROOT / "sources.json").write_text(json.dumps(results, indent=2) + "\n")
for r in results:
    print(r["name"], r.get("status", r.get("error")))
