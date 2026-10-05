from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(
        "VAANI_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
    )
    monkeypatch.setenv("VAANI_AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("VAANI_REDIS_ENABLED", "false")
    monkeypatch.setenv("VAANI_LOCAL_VOICE_ENABLED", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()
