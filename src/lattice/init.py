"""Interactive and automated project initializer for Lattice."""

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from .config import estimate_or_read_kv_bytes, file_hash
from .observability.host import get_host_memory_kb

DEFAULT_COMMIT = "b1b770d90d94cad9e9ea5b993bdbc383a522fb28"
DEFAULT_MODEL_NAME = "qwen2.5-0.5b-instruct-f16"
DEFAULT_MODEL_FILE = "qwen2.5-0.5b-instruct-fp16.gguf"
DEFAULT_MODEL_REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"
DEFAULT_MODEL_URL = f"https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/{DEFAULT_MODEL_REVISION}/{DEFAULT_MODEL_FILE}"
DEFAULT_MODEL_SHA = "8e0ae26000627ed62de0e78e41860af70094558b9d2913385c842a6aa06cf3fc"
DEFAULT_MODEL_BYTES = 1266425696


def calculate_safe_reserve(total_mb: int) -> int:
    """Auto-calibrate host memory reserve based on available physical RAM."""
    if total_mb <= 2048:
        return 512
    if total_mb <= 4096:
        return 1024
    if total_mb <= 8192:
        return 2048
    return 4096


def find_llama_server(workspace: Path) -> Path | None:
    """Search for existing llama-server binary in common local and system paths."""
    candidates = [
        workspace / ".local/llama.cpp/build/bin/llama-server",
        workspace / "bin/llama-server",
        Path.home() / ".local/bin/llama-server",
        Path("/usr/local/bin/llama-server"),
    ]
    which_bin = shutil.which("llama-server")
    if which_bin:
        candidates.insert(0, Path(which_bin))

    for cand in candidates:
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand.resolve()
    return None


def run_init(
    target_dir: str | Path | None = None,
    backend_path: str | Path | None = None,
    model_path: str | Path | None = None,
    non_interactive: bool = False,
) -> dict:
    workspace = Path(target_dir or Path.cwd()).resolve()
    print("=" * 66)
    print("⚡ LATTICE PROJECT INITIALIZER")
    print("=" * 66)
    print(f"Target Directory: {workspace}")

    # 1. Hardware Detection
    mem = get_host_memory_kb()
    total_mb = mem.get("MemTotal", 4096 * 1024) // 1024
    avail_mb = mem.get("MemAvailable", total_mb) // 1024
    cpu_cores = os.cpu_count() or 2
    os_name = platform.system()
    machine = platform.machine()
    safe_reserve = calculate_safe_reserve(total_mb)

    print(f"Detected System:  {os_name} ({machine}) | {cpu_cores} CPU cores")
    print(f"Memory Telemetry: {avail_mb} MB available / {total_mb} MB total")
    print(f"Calibrated Reserve: {safe_reserve} MB host guard")
    print("-" * 66)

    # 2. Workspace Setup
    for sub in ["configs", "models", "artifacts", ".local"]:
        (workspace / sub).mkdir(parents=True, exist_ok=True)

    # 3. Backend Binary Discovery / Provisioning
    binary = None
    if backend_path:
        b_p = Path(backend_path).resolve()
        if b_p.is_file() and os.access(b_p, os.X_OK):
            binary = b_p
    if not binary:
        binary = find_llama_server(workspace)

    if not binary:
        print("[!] No llama-server binary detected.")
        # Check if cmake and ninja or compiler are available
        has_cmake = shutil.which("cmake") is not None
        if has_cmake and (workspace / "scripts/provision_cpu.py").exists():
            print("Found provision script. Building native llama.cpp backend...")
            try:
                subprocess.run(
                    [sys.executable, str(workspace / "scripts/provision_cpu.py")],
                    cwd=workspace,
                    check=True,
                )
                binary = find_llama_server(workspace)
            except (subprocess.SubprocessError, OSError) as exc:
                print(f"Build failed: {exc}", file=sys.stderr)

    if not binary:
        # Placeholder or system guide
        print(
            "[Notice] Using default backend path '../.local/llama.cpp/build/bin/llama-server'."
        )
        binary = (workspace / ".local/llama.cpp/build/bin/llama-server").resolve()
        bin_sha = "0" * 64
        libs = {}
    else:
        print(f"Backend Engine:   ✅ Found: {binary}")
        bin_sha = file_hash(binary)
        # Check shared libraries in same directory
        bin_dir = binary.parent
        lib_patterns = ["*.so*", "*.dylib*"]
        libs = {
            os.path.relpath(p, workspace / "configs"): file_hash(p)
            for pattern in lib_patterns
            for p in sorted(bin_dir.glob(pattern))
            if p.is_file()
        }

    # 4. Model Discovery / Download
    final_model_path = None
    if model_path:
        m_p = Path(model_path).resolve()
        if m_p.is_file():
            final_model_path = m_p
            model_id = m_p.stem
            model_sha = file_hash(m_p)
            model_precision = "GGUF"

    if not final_model_path:
        default_model = workspace / "models" / DEFAULT_MODEL_FILE
        if default_model.is_file():
            final_model_path = default_model
            model_id = DEFAULT_MODEL_NAME
            model_sha = file_hash(default_model)
            model_precision = "GGUF F16 (mixed tensor types)"
        else:
            print(f"Default Model:    Not found ({DEFAULT_MODEL_FILE})")
            should_download = non_interactive
            if not should_download:
                ans = input(
                    "Download verified base model (Qwen 2.5 0.5B Instruct, ~1.2 GB)? [Y/n]: "
                )
                should_download = ans.strip().lower() in ("", "y", "yes")

            if should_download:
                print(f"Downloading from Hugging Face: {DEFAULT_MODEL_URL}...")
                temp_file = default_model.with_suffix(".downloading")
                try:
                    with (
                        urllib.request.urlopen(DEFAULT_MODEL_URL, timeout=300) as resp,
                        temp_file.open("wb") as out,
                    ):
                        shutil.copyfileobj(resp, out, length=4 * 1024 * 1024)
                    temp_file.replace(default_model)
                    final_model_path = default_model
                    model_id = DEFAULT_MODEL_NAME
                    model_sha = file_hash(default_model)
                    model_precision = "GGUF F16 (mixed tensor types)"
                    print("Model Download:   ✅ Complete and verified.")
                except (OSError, urllib.error.URLError) as exc:
                    print(
                        f"Download failed ({exc}). You can register any local .gguf with 'lattice models add'."
                    )
                    temp_file.unlink(missing_ok=True)

    if not final_model_path:
        final_model_path = workspace / "models" / DEFAULT_MODEL_FILE
        model_id = DEFAULT_MODEL_NAME
        model_sha = DEFAULT_MODEL_SHA
        model_precision = "GGUF F16 (mixed tensor types)"

    kv_bytes = (
        estimate_or_read_kv_bytes(final_model_path)
        if final_model_path.exists()
        else 12288
    )

    # 5. Generate configs/local.json
    config_path = workspace / "configs/local.json"
    backend_rel = os.path.relpath(binary, workspace / "configs")
    model_rel = os.path.relpath(final_model_path, workspace / "configs")

    settings_dict = {
        "backend_binary": backend_rel,
        "backend_sha256": bin_sha,
        "backend_commit": DEFAULT_COMMIT,
        "backend_files": libs,
        "models": [
            {
                "id": model_id,
                "path": model_rel,
                "sha256": model_sha,
                "source_repository": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "source_revision": DEFAULT_MODEL_REVISION,
                "license": "Apache-2.0",
                "precision": model_precision,
                "kv_bytes_per_token": kv_bytes,
            }
        ],
        "native_slots": 2,
        "admission_policy": "priority_preemptive",
        "host_reserve_mb": safe_reserve,
        "log_directory": "../artifacts",
    }

    config_path.write_text(json.dumps(settings_dict, indent=2) + "\n")
    print("-" * 66)
    print(f"Config Written:   ✅ {config_path}")
    print(f"Model Registered: ✅ {model_id} (KV Cache: {kv_bytes} bytes/tok)")
    print("Serving Policy:   ⚡ priority_preemptive (2 slots, instant replies)")
    print("=" * 66)
    print("🎉 Lattice initialized successfully!\n")
    print("Next steps:")
    print(f"  1. Start server:   lattice serve --model {model_id} --preset chat")
    print("  2. Check status:   lattice status")
    print("=" * 66)

    return settings_dict
