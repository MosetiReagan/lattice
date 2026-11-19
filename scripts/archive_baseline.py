"""Archive the frozen standard source without any weights, binaries or secrets."""

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
commit = (root / "benchmarks/baseline/standard-runtime-commit.txt").read_text().strip()
metadata = json.loads((root / "benchmarks/baseline/manifest.json").read_text())
files = subprocess.check_output(
    ["git", "ls-tree", "-r", "--name-only", commit], cwd=root, text=True
).splitlines()
selected = [
    p
    for p in files
    if p.startswith(
        (
            "src/",
            "tests/",
            "scripts/",
            "configs/",
            "benchmarks/datasets/",
            "benchmarks/workloads/",
        )
    )
    or p in ["pyproject.toml", "uv.lock", "LICENSE", "NOTICE", "README.md"]
]
output = root / "benchmarks/baseline/standard-source.tar.gz"
if output.exists():
    if hashlib.sha256(output.read_bytes()).hexdigest() != metadata.get(
        "source_archive_sha256"
    ):
        raise SystemExit(
            "Existing frozen archive checksum mismatch; refusing to overwrite"
        )
    print(output)
    raise SystemExit(0)
with tarfile.open(output, "w:gz") as archive:
    for name in sorted(selected):
        data = subprocess.check_output(["git", "show", commit + ":" + name], cwd=root)
        expected = metadata["source"]["files"].get(name)
        if expected and hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit("Frozen source hash mismatch")
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o644
        info.mtime = 0
        archive.addfile(info, io.BytesIO(data))
metadata["source_archive_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
(root / "benchmarks/baseline/manifest.json").write_text(
    json.dumps(metadata, indent=2) + "\n"
)
print(output)
