from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from planogram.app import create_app
from planogram.settings import Settings

API_KEY = "test-service-key"


def headers(role: str = "Manager", user_id: str = "user-1") -> dict[str, str]:
    return {"X-API-Key": API_KEY, "X-User-Id": user_id, "X-User-Role": role}


MANAGER = headers("Manager", "manager-1")
OPERATOR = headers("Operator", "operator-1")
VIEWER = headers("Viewer", "viewer-1")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key=API_KEY,
        db_path=tmp_path / "planogram.sqlite",
        image_dir=tmp_path / "images",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
