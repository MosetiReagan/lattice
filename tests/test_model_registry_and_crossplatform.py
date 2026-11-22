"""Tests for cross-platform host telemetry and dynamic model registration."""

from pathlib import Path

import pytest

from lattice.config import (
    load_settings,
    register_model,
    select_model,
)
from lattice.observability.hardware import cpu_fingerprint
from lattice.observability.host import get_host_memory_kb, read_cpu_times
from lattice.types import LatticeError


def test_select_model_by_registered_id_and_filename(settings):
    # Registered ID
    entry = select_model(settings, "test-model")
    assert entry.id == "test-model"

    # Match by filename stem or path
    filename = Path(entry.path).name
    assert select_model(settings, filename).id == "test-model"
    assert select_model(settings, Path(entry.path).stem).id == "test-model"


def test_select_model_auto_registers_arbitrary_gguf_file(settings, tmp_path):
    dummy_model = tmp_path / "custom-llama-3.2-1b-instruct.q4_k_m.gguf"
    dummy_model.write_bytes(b"GGUF" + b"\x00" * 1024)

    # Calling select_model with an arbitrary file path auto-registers it
    entry = select_model(settings, str(dummy_model))
    assert entry.path == str(dummy_model.resolve())
    assert entry.precision == "GGUF Q4_K_M"
    assert len(entry.sha256) == 64

    # The registered model is now discoverable by its ID and filename
    assert select_model(settings, entry.id).sha256 == entry.sha256


def test_register_model_and_persist(settings, tmp_path):
    config_file = tmp_path / "configs" / "local.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(settings.model_dump_json(indent=2))

    dummy_model = tmp_path / "mistral-7b-v0.3-q8_0.gguf"
    dummy_model.write_bytes(b"GGUF" + b"\x01" * 2048)

    parsed = load_settings(config_file)
    entry = register_model(
        parsed,
        source=str(dummy_model),
        name="my-mistral",
        precision="GGUF Q8_0",
        save=True,
        config_path=config_file,
    )
    assert entry.id == "my-mistral"
    assert entry.precision == "GGUF Q8_0"

    # Verify persisted in config
    reloaded = load_settings(config_file)
    assert any(m.id == "my-mistral" for m in reloaded.models)


def test_select_model_rejects_nonexistent_files(settings):
    with pytest.raises(LatticeError, match="not registered"):
        select_model(settings, "/nonexistent/path/to/missing_model.gguf")


def test_crossplatform_host_memory_telemetry():
    mem = get_host_memory_kb()
    assert "MemTotal" in mem
    assert "MemAvailable" in mem
    assert mem["MemTotal"] > 0
    assert mem["MemAvailable"] > 0


def test_crossplatform_cpu_times():
    times = read_cpu_times()
    assert times.total > 0
    assert times.steal >= 0


def test_crossplatform_cpu_fingerprint():
    fp = cpu_fingerprint()
    assert len(fp) == 64


def test_macos_telemetry_fallbacks_when_proc_missing(monkeypatch):
    # Simulate a macOS environment where /proc does not exist
    orig_exists = Path.exists

    def mock_exists(self):
        if str(self).startswith("/proc"):
            return False
        return orig_exists(self)

    monkeypatch.setattr(Path, "exists", mock_exists)

    # get_host_memory_kb falls back to sysconf / vm_stat without error
    mem = get_host_memory_kb()
    assert "MemTotal" in mem
    assert "MemAvailable" in mem
    assert mem["MemTotal"] > 0

    # read_cpu_times falls back without crashing
    times = read_cpu_times()
    assert times.total > 0

    # cpu_fingerprint falls back without crashing
    fp = cpu_fingerprint()
    assert len(fp) == 64
