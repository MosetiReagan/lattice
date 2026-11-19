"""Derive Q8_0/Q4_K_M from the exact frozen FP16 artifact, with provenance."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from lattice.config import file_hash, load_settings
from lattice.optimizations.speculative.compatibility import tokenizer_fingerprint

p = argparse.ArgumentParser()
p.add_argument("format", choices=["Q8_0", "Q4_K_M"])
args = p.parse_args()
root = Path(__file__).resolve().parents[1]
settings = load_settings(root / "configs/local.json")
original = settings.models[0]
source = Path(original.path)
if file_hash(source) != original.sha256:
    raise SystemExit("Source artifact checksum mismatch")
if shutil.disk_usage(root).free < 3 * 1024**3 + source.stat().st_size:
    raise SystemExit("Insufficient disk reserve")
label = args.format.lower()
destination = root / "models" / f"qwen2.5-0.5b-instruct-{label}.gguf"
if destination.exists():
    raise SystemExit("Destination exists; do not overwrite derived artifacts")
tool = root / ".local/llama.cpp/build/bin/llama-quantize"
command = [str(tool), str(source), str(destination), args.format, "4"]
subprocess.run(command, check=True)
fingerprint = tokenizer_fingerprint(source)
if tokenizer_fingerprint(destination) != fingerprint:
    raise SystemExit("Tokenizer changed; derived artifact rejected")
model_id = f"qwen2.5-0.5b-instruct-{label}"
config = root / "configs/local.json"
raw = json.loads(config.read_text())
entry = original.model_dump()
entry.update(
    id=model_id,
    path="../models/" + destination.name,
    sha256=file_hash(destination),
    precision="GGUF " + args.format,
)
raw["models"].append(entry)
config.write_text(json.dumps(raw, indent=2) + "\n")
manifest = {
    "source_sha256": original.sha256,
    "candidate_sha256": entry["sha256"],
    "format": args.format,
    "source_bytes": source.stat().st_size,
    "candidate_bytes": destination.stat().st_size,
    "tool_sha256": file_hash(tool),
    "backend_commit": settings.backend_commit,
    "tokenizer_fingerprint": fingerprint,
    "command": command,
    "note": "Locally derived from the identical frozen FP16 GGUF; no calibrated quality guarantee.",
}
(root / "artifacts" / f"quantization-{label}.json").write_text(
    json.dumps(manifest, indent=2) + "\n"
)
print(json.dumps(manifest, indent=2))
