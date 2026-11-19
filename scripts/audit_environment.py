"""Read-only local inventory; never dumps environment variables or secrets."""

import datetime
import importlib.metadata
import json
import pathlib
import platform
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def command(args):
    if shutil.which(args[0]) is None:
        return {"available": False}
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=30, check=False
    )
    return {
        "available": True,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


report = {
    "captured_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    "python": platform.python_version(),
    "platform": platform.platform(),
    "commands": {},
    "packages": {},
}
for args in [
    ["lscpu"],
    ["free", "-b"],
    ["df", "-B1", str(ROOT)],
    ["nvidia-smi"],
    ["nvcc", "--version"],
    ["cmake", "--version"],
    ["gcc", "--version"],
    ["g++", "--version"],
    ["git", "--version"],
]:
    report["commands"][" ".join(args)] = command(args)
for name in [
    "torch",
    "transformers",
    "vllm",
    "sglang",
    "llama-cpp-python",
    "onnxruntime",
    "bitsandbytes",
    "huggingface-hub",
]:
    try:
        report["packages"][name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        report["packages"][name] = None
report["device_nodes"] = [str(p) for p in pathlib.Path("/dev").glob("nvidia*")]
report["dri_present"] = pathlib.Path("/dev/dri").exists()
report["cgroup_v2"] = {}
for name in ["memory.max", "cpu.max"]:
    path = pathlib.Path("/sys/fs/cgroup") / name
    report["cgroup_v2"][name] = path.read_text().strip() if path.exists() else None
output = ROOT / "docs" / "evidence" / "environment.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + "\n")
print(output)
