"""Provision the fixed, tested 1.5B Q8 target without downloading FP16 weights."""

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
name = "qwen2.5-1.5b-instruct-q8_0.gguf"
revision = "91cad51170dc346986eccefdc2dd33a9da36ead9"
expected = "d7efb072e7724d25048a4fda0a3e10b04bdef5d06b1403a1c93bd9f1240a63c8"
size = 1894532128
path = root / "models" / name
url = (
    f"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/{revision}/{name}"
)
if not path.exists():
    if shutil.disk_usage(root).free < size + 3 * 1024**3:
        raise SystemExit("Need target space plus 3 GiB disk reserve")
    temporary = path.with_suffix(".partial")
    try:
        digest = hashlib.sha256()
        with (
            urllib.request.urlopen(url, timeout=120) as reply,
            temporary.open("wb") as out,
        ):
            while data := reply.read(4 * 1024**2):
                out.write(data)
                digest.update(data)
        if temporary.stat().st_size != size or digest.hexdigest() != expected:
            raise SystemExit("Target checksum/size mismatch")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
digest = hashlib.sha256()
with path.open("rb") as source:
    for data in iter(lambda: source.read(4 * 1024**2), b""):
        digest.update(data)
if path.stat().st_size != size or digest.hexdigest() != expected:
    raise SystemExit("Existing target checksum mismatch")
config = root / "configs/local.json"
settings = json.loads(config.read_text())
model_id = "qwen2.5-1.5b-instruct-q8"
if not any(m["id"] == model_id for m in settings["models"]):
    settings["models"].append(
        {
            "id": model_id,
            "path": "../models/" + name,
            "sha256": expected,
            "source_repository": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
            "source_revision": revision,
            "license": "Apache-2.0",
            "precision": "GGUF Q8_0",
            "kv_bytes_per_token": 28672,
        }
    )
config.write_text(json.dumps(settings, indent=2) + "\n")
print("Verified and registered", model_id)
