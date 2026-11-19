"""Operator-only model registry. The HTTP API never accepts artifact paths."""

import hashlib
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

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
    draft_model_id: str | None = None
    draft_tokens: int = Field(default=4, ge=1, le=16)
    context_tokens: int = Field(default=2048, ge=128, le=8192)
    threads: int = Field(default=4, ge=1, le=64)
    native_slots: int = Field(default=1, ge=1, le=4)
    max_queue: int = Field(default=8, ge=0, le=128)
    worker_address_space_mb: int = Field(default=4096, ge=1024)
    host_reserve_mb: int = Field(default=2048, ge=256)
    startup_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    log_directory: str = "artifacts"
    requests_per_minute: int = Field(default=60, ge=1, le=100000)


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


def select_model(settings: Settings, model_id: str) -> ModelEntry:
    for entry in settings.models:
        if entry.id == model_id:
            return entry
    raise LatticeError(f"Model {model_id!r} is not registered", 404, "model_not_found")


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
