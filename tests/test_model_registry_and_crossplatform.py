"""Tests for cross-platform host telemetry and dynamic model registration."""

import json
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


def test_auto_registers_kv_bytes_per_token(settings, tmp_path):
    dummy_model = tmp_path / "custom-llama-3.2-1b-instruct.q4_k_m.gguf"
    dummy_model.write_bytes(b"GGUF" + b"\x00" * 1024)

    entry = select_model(settings, str(dummy_model))
    assert entry.kv_bytes_per_token is not None
    assert entry.kv_bytes_per_token > 0


def test_actionable_memory_guard_suggestion(settings, monkeypatch, tmp_path):
    backend_bin = tmp_path / "llama-server"
    backend_bin.write_bytes(b"mock_bin")
    dummy_model = tmp_path / "model.gguf"
    dummy_model.write_bytes(b"mock_model")

    from lattice.backends.llama_cpp import LlamaCppBackend

    settings.backend_binary = str(backend_bin)
    settings.backend_sha256 = "0" * 64
    settings.backend_files = {}
    entry = settings.models[0]
    entry.path = str(dummy_model)
    entry.sha256 = "0" * 64

    monkeypatch.setattr("lattice.backends.llama_cpp.file_hash", lambda p: "0" * 64)

    backend = LlamaCppBackend(settings, entry)

    # Force low memory
    monkeypatch.setattr(
        "lattice.observability.host.get_host_memory_kb",
        lambda: {"MemTotal": 4096 * 1024, "MemAvailable": 512 * 1024},
    )
    with pytest.raises(LatticeError) as exc_info:
        import asyncio

        asyncio.run(backend.start())
    assert exc_info.value.status == 503
    assert "Suggestion: rerun with --host-reserve-mb" in str(exc_info.value)


def test_cli_status_command(settings, tmp_path, monkeypatch, capsys):
    from lattice.cli import main

    config_file = tmp_path / "configs" / "local.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(settings.model_dump_json(indent=2))

    monkeypatch.setattr(
        "sys.argv", ["lattice", "--config", str(config_file), "status", "--json"]
    )
    main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "server" in data
    assert "host" in data
    assert "models" in data
    assert data["host"]["cpu_count"] > 0
    assert data["host"]["total_memory_mb"] > 0

    # Text mode
    monkeypatch.setattr("sys.argv", ["lattice", "--config", str(config_file), "status"])
    main()
    text_out = capsys.readouterr().out
    assert "LATTICE SYSTEM & SERVER STATUS" in text_out
    assert "Registered Models" in text_out


def test_init_command(tmp_path, monkeypatch, capsys):
    from lattice.cli import main
    from lattice.init import calculate_safe_reserve

    assert calculate_safe_reserve(2048) == 512
    assert calculate_safe_reserve(4096) == 1024
    assert calculate_safe_reserve(8192) == 2048
    assert calculate_safe_reserve(16384) == 4096

    dummy_model = tmp_path / "my-test.gguf"
    dummy_model.write_bytes(b"GGUF" + b"\x00" * 1024)

    target_dir = tmp_path / "my_project"
    monkeypatch.setattr(
        "sys.argv",
        [
            "lattice",
            "init",
            "--dir",
            str(target_dir),
            "--model-path",
            str(dummy_model),
            "-y",
        ],
    )
    main()
    captured = capsys.readouterr().out
    assert "LATTICE PROJECT INITIALIZER" in captured
    assert "Lattice initialized successfully!" in captured

    config_path = target_dir / "configs/local.json"
    assert config_path.is_file()
    data = json.loads(config_path.read_text())
    assert data["admission_policy"] == "priority_preemptive"
    assert data["native_slots"] == 2
    assert len(data["models"]) == 1
    assert data["models"][0]["id"] == "my-test"
    assert data["models"][0]["kv_bytes_per_token"] > 0
