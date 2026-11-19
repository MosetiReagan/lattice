import pytest

from lattice.config import ModelEntry, Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        backend_binary="/not/used",
        backend_sha256="0" * 64,
        backend_commit="test",
        models=[
            ModelEntry(
                id="test-model",
                path="/not/used",
                sha256="0" * 64,
                source_repository="test/model",
                source_revision="test",
                license="test",
                precision="test",
            )
        ],
        log_directory=str(tmp_path),
        max_queue=1,
    )
