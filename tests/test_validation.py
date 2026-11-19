import json

import pytest
from pydantic import ValidationError

from lattice.config import load_settings, select_model
from lattice.types import GenerationRequest, LatticeError


@pytest.mark.parametrize(
    "change",
    [
        {"max_tokens": 0},
        {"max_tokens": 513},
        {"max_tokens": True},
        {"temperature": float("nan")},
        {"temperature": -1.0},
        {"prompt": "x" * 32769},
        {"prompt": "界" * 12000},
        {"messages": [{"role": "user", "content": "hello"}]},
        {"optimization": {"mode": "adaptive"}},
        {"top_p": 0.5},
    ],
)
def test_invalid_input(change):
    data = {"model": "test-model", "prompt": "Hello"} | change
    with pytest.raises(ValidationError):
        GenerationRequest(**data)


def test_missing_and_chat_inputs():
    with pytest.raises(ValidationError):
        GenerationRequest(model="x")
    request = GenerationRequest(
        model="x", messages=[{"role": "user", "content": "Hello"}]
    )
    assert request.prompt is None


def test_registry_paths_and_unknown_model(settings, tmp_path):
    data = settings.model_dump()
    data["backend_binary"] = "../binary"
    data["models"][0]["path"] = "../model"
    path = tmp_path / "registry" / "config.json"
    path.parent.mkdir()
    path.write_text(json.dumps(data))
    parsed = load_settings(path)
    assert parsed.backend_binary == str(tmp_path / "binary")
    assert parsed.models[0].path == str(tmp_path / "model")
    with pytest.raises(LatticeError, match="not registered"):
        select_model(parsed, "../arbitrary")
    data["models"] *= 2
    path.write_text(json.dumps(data))
    with pytest.raises(LatticeError, match="duplicate"):
        load_settings(path)
