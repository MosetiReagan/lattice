"""Model registry and dynamic model registration for Lattice."""

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .types import LatticeError


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_repository: str
    source_revision: str
    license: str
    kv_bytes_per_token: int | None = Field(default=None, gt=0)
    precision: str


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    backend_binary: str
    backend_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    backend_commit: str
    backend_files: dict[str, str] = Field(default_factory=dict)
    models: list[ModelEntry] = Field(min_length=1)
    policy_file: str | None = None
    cache_limit_mb: int = Field(default=32, ge=1, le=4096)
    cache_min_tokens: int = Field(default=64, ge=1)
    concurrent_prefix_cache: bool = False
    native_ram_prompt_archive: bool = True
    draft_model_id: str | None = None
    draft_tokens: int = Field(default=4, ge=1, le=16)
    context_tokens: int = Field(default=2048, ge=128, le=8192)
    threads: int = Field(default=4, ge=1, le=64)
    batch_tokens: int = Field(default=256, ge=32, le=2048)
    ubatch_tokens: int = Field(default=256, ge=32, le=2048)
    native_slots: Literal[1, 2, 3, 4, 8] = 1
    max_queue: int = Field(default=8, ge=0, le=128)
    admission_policy: Literal[
        "priority_fifo",
        "priority_cost",
        "priority_cost_reserve",
        "priority_cost_coalesce",
        "priority_preemptive",
    ] = "priority_fifo"
    preemption_auto_resume: bool = True
    worker_address_space_mb: int = Field(default=4096, ge=1024)
    host_reserve_mb: int = Field(default=2048, ge=256)
    startup_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    log_directory: str = "artifacts"
    requests_per_minute: int = Field(default=60, ge=1, le=100000)

    @model_validator(mode="after")
    def valid_native_batch(self):
        if self.ubatch_tokens > self.batch_tokens:
            raise ValueError("ubatch_tokens cannot exceed batch_tokens")
        return self


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_settings(path: str | Path | None = None) -> Settings:
    config_path = Path(
        path or os.environ.get("LATTICE_CONFIG", "configs/local.json")
    ).resolve()
    try:
        settings = Settings.model_validate_json(config_path.read_text())
    except (OSError, ValueError) as exc:
        raise LatticeError(f"Cannot load registry {config_path}: {exc}") from exc
    # Registry relative paths are relative to the registry's parent, not process cwd.
    for model in settings.models:
        model.path = str((config_path.parent / model.path).resolve())
    settings.backend_binary = str(
        (config_path.parent / settings.backend_binary).resolve()
    )
    settings.backend_files = {
        str((config_path.parent / k).resolve()): v
        for k, v in settings.backend_files.items()
    }
    if settings.policy_file is not None:
        settings.policy_file = str(
            (config_path.parent / settings.policy_file).resolve()
        )
    settings.log_directory = str(
        (config_path.parent / settings.log_directory).resolve()
    )
    if len({m.id for m in settings.models}) != len(settings.models):
        raise LatticeError("Registry contains duplicate model IDs")
    return settings


def detect_precision(name: str) -> str:
    lower = name.lower()
    for tag in [
        "q4_k_m",
        "q4_k_s",
        "q4_0",
        "q4_1",
        "q5_k_m",
        "q5_k_s",
        "q5_0",
        "q5_1",
        "q6_k",
        "q8_0",
        "q8_1",
        "f16",
        "f32",
        "bf16",
    ]:
        if tag in lower:
            return f"GGUF {tag.upper()}"
    return "GGUF"


def auto_register_file_model(
    settings: Settings, path: Path, model_id: str | None = None
) -> ModelEntry:
    resolved = path.resolve()
    sha = file_hash(resolved)
    for m in settings.models:
        if m.sha256 == sha:
            return m
    precision = detect_precision(resolved.name)
    entry_id = (
        model_id
        if (model_id and "/" not in model_id and "\\" not in model_id)
        else resolved.stem
    )
    entry = ModelEntry(
        id=entry_id,
        path=str(resolved),
        sha256=sha,
        source_repository=f"local/{resolved.stem}",
        source_revision="local",
        license="custom",
        precision=precision,
        kv_bytes_per_token=None,
    )
    settings.models = [m for m in settings.models if m.id != entry_id] + [entry]
    return entry


def select_model(settings: Settings, model_id: str) -> ModelEntry:
    for entry in settings.models:
        if entry.id == model_id:
            return entry
    for entry in settings.models:
        p = Path(entry.path)
        if model_id in (p.name, p.stem, str(p)):
            return entry
    candidate_paths = [
        Path(model_id),
        Path.cwd() / model_id,
        Path("models") / model_id,
        Path("models") / f"{model_id}.gguf",
    ]
    for cand in candidate_paths:
        try:
            if cand.is_file():
                return auto_register_file_model(settings, cand, model_id=model_id)
        except OSError:
            pass
    raise LatticeError(f"Model {model_id!r} is not registered", 404, "model_not_found")


def register_model(
    settings: Settings,
    source: str,
    name: str | None = None,
    precision: str | None = None,
    save: bool = True,
    config_path: str | Path | None = None,
) -> ModelEntry:
    resolved_config = Path(
        config_path or os.environ.get("LATTICE_CONFIG", "configs/local.json")
    ).resolve()

    if source.startswith(("http://", "https://")):
        models_dir = resolved_config.parent.parent / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        filename = source.rstrip("/").split("/")[-1] or "downloaded-model.gguf"
        target_path = models_dir / filename
        temp_path = target_path.with_suffix(".downloading")
        try:
            with urllib.request.urlopen(source, timeout=300) as resp, temp_path.open("wb") as out:
                shutil.copyfileobj(resp, out, length=4 * 1024 * 1024)
            temp_path.replace(target_path)
        finally:
            temp_path.unlink(missing_ok=True)
        local_path = target_path
    else:
        local_path = Path(source).resolve()
        if not local_path.is_file():
            raise LatticeError(f"Model file does not exist: {source}", 404, "file_not_found")

    sha = file_hash(local_path)
    entry_id = name or local_path.stem
    entry_precision = precision or detect_precision(local_path.name)

    entry = ModelEntry(
        id=entry_id,
        path=str(local_path),
        sha256=sha,
        source_repository=f"local/{local_path.stem}",
        source_revision="local",
        license="custom",
        precision=entry_precision,
        kv_bytes_per_token=None,
    )

    settings.models = [m for m in settings.models if m.id != entry_id] + [entry]

    if save and resolved_config.exists():
        try:
            data = json.loads(resolved_config.read_text())
            model_rel = os.path.relpath(local_path, resolved_config.parent)
            model_dict = {
                "id": entry.id,
                "path": model_rel,
                "sha256": entry.sha256,
                "source_repository": entry.source_repository,
                "source_revision": entry.source_revision,
                "license": entry.license,
                "precision": entry.precision,
            }
            existing_models = [m for m in data.get("models", []) if m.get("id") != entry_id]
            existing_models.append(model_dict)
            data["models"] = existing_models
            resolved_config.write_text(json.dumps(data, indent=2) + "\n")
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass

    return entry


def public_model(entry: ModelEntry) -> dict:
    return {
        "id": entry.id,
        "object": "model",
        "owned_by": entry.source_repository.split("/")[0],
        "backend": "llama.cpp",
        "precision": entry.precision,
        "license": entry.license,
        "source_repository": entry.source_repository,
        "source_revision": entry.source_revision,
    }
