"""Reproduce the tested CPU backend and official FP16 model. No model Python is loaded.

Run with the project environment after `uv sync --extra dev --extra provision`.
Downloads ~1.2 GiB of weights. Existing artifacts are checked, never blindly replaced.
"""

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b1b770d90d94cad9e9ea5b993bdbc383a522fb28"
MODEL_REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"
MODEL_FILE = "qwen2.5-0.5b-instruct-fp16.gguf"
MODEL_SHA = "8e0ae26000627ed62de0e78e41860af70094558b9d2913385c842a6aa06cf3fc"
MODEL_BYTES = 1266425696


def run(args, cwd=ROOT):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(4 * 1024**2), b""):
            digest.update(data)
    return digest.hexdigest()


def main():
    for name in [".local", "models", "artifacts", "configs"]:
        (ROOT / name).mkdir(exist_ok=True)
    if shutil.disk_usage(ROOT).free < 3 * 1024**3 + MODEL_BYTES:
        raise SystemExit("Need model space plus at least 3 GiB free reserve")
    cmake, ninja = (
        Path(sys.executable).parent / "cmake",
        Path(sys.executable).parent / "ninja",
    )
    if not cmake.exists() or not ninja.exists():
        raise SystemExit("Run uv sync --extra dev --extra provision first")
    source = ROOT / ".local/llama.cpp"
    if not source.exists():
        source.mkdir()
        run(["git", "init", source])
        run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://github.com/ggml-org/llama.cpp.git",
            ],
            source,
        )
        run(["git", "fetch", "--depth", "1", "origin", COMMIT], source)
        run(["git", "checkout", "--detach", COMMIT], source)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source, text=True
    ).strip()
    if actual != COMMIT:
        raise SystemExit(
            "Existing llama.cpp checkout has a different commit; use a separate workspace"
        )
    run(["git", "diff", "--exit-code", "HEAD"], source)
    flags = [
        "-G",
        "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DGGML_CUDA=OFF",
        "-DGGML_NATIVE=ON",
        "-DLLAMA_BUILD_TESTS=OFF",
        "-DLLAMA_BUILD_EXAMPLES=OFF",
        "-DLLAMA_BUILD_TOOLS=ON",
        "-DLLAMA_BUILD_SERVER=ON",
        "-DLLAMA_OPENSSL=OFF",
        "-DLLAMA_BUILD_UI=OFF",
        "-DLLAMA_USE_PREBUILT_UI=OFF",
    ]
    # Refuse stale UI downloads from an earlier build instead of embedding them accidentally.
    if (source / "build/tools/ui/dist/index.html").exists():
        raise SystemExit(
            "Stale generated UI assets exist; clean the backend build directory first"
        )
    run([cmake, "-S", source, "-B", source / "build", *flags])
    run(
        [
            cmake,
            "--build",
            source / "build",
            "--target",
            "llama-server",
            "llama-bench",
            "-j",
            "3",
        ]
    )
    model = ROOT / "models" / MODEL_FILE
    url = f"https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/{MODEL_REVISION}/{MODEL_FILE}"
    if not model.exists():
        temporary = model.with_suffix(".partial")
        try:
            with (
                urllib.request.urlopen(url, timeout=120) as reply,
                temporary.open("wb") as out,
            ):
                shutil.copyfileobj(reply, out, length=4 * 1024**2)
            if temporary.stat().st_size != MODEL_BYTES or sha(temporary) != MODEL_SHA:
                raise SystemExit("Downloaded model checksum/size mismatch")
            temporary.replace(model)
        finally:
            temporary.unlink(missing_ok=True)
    if model.stat().st_size != MODEL_BYTES or sha(model) != MODEL_SHA:
        raise SystemExit("Existing model checksum/size mismatch; refusing to overwrite")
    binary = source / "build/bin/llama-server"
    libs = {
        os.path.relpath(p, ROOT / "configs"): sha(p)
        for p in sorted((source / "build/bin").glob("*.so*"))
        if p.is_file()
    }
    settings = {
        "backend_binary": os.path.relpath(binary, ROOT / "configs"),
        "backend_sha256": sha(binary),
        "backend_commit": COMMIT,
        "backend_files": libs,
        "models": [
            {
                "id": "qwen2.5-0.5b-instruct-f16",
                "path": os.path.relpath(model, ROOT / "configs"),
                "sha256": MODEL_SHA,
                "source_repository": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "source_revision": MODEL_REVISION,
                "license": "Apache-2.0",
                "precision": "GGUF F16 (mixed tensor types)",
                "kv_bytes_per_token": 12288,
            }
        ],
        "log_directory": "../artifacts",
    }
    (ROOT / "configs/local.json").write_text(json.dumps(settings, indent=2) + "\n")
    metadata = {
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "backend_commit": COMMIT,
        "cmake_flags": flags,
        "backend_binary_sha256": settings["backend_sha256"],
        "shared_libraries": libs,
        "model_url": url,
        "model_sha256": MODEL_SHA,
        "model_bytes": MODEL_BYTES,
        "note": "Native CPU build: hashes are build-specific; this is not a frozen benchmark.",
    }
    (ROOT / "artifacts/backend-build.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    for name, args in [
        ("backend-help.txt", ["--help"]),
        ("backend-version.txt", ["--version"]),
    ]:
        with (ROOT / "artifacts" / name).open("w") as out:
            subprocess.run(
                [binary, *args], stdout=out, stderr=subprocess.STDOUT, check=True
            )
    print("Provisioned verified CPU model and backend; registry: configs/local.json")


if __name__ == "__main__":
    main()
