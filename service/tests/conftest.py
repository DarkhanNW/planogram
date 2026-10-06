from pathlib import Path
from typing import Iterator

import cv2
import httpx
import numpy as np
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


def import_catalogue(
    client: TestClient, csv: str, images: dict[str, bytes], who: dict[str, str] = MANAGER
) -> httpx.Response:
    files = [("csv", ("products.csv", csv.encode(), "text/csv"))]
    files += [("images", (name, data, "image/jpeg")) for name, data in images.items()]
    return client.post("/products/import", files=files, headers=who)


def jpeg(color: tuple[int, int, int] = (0, 128, 255), size: tuple[int, int] = (40, 30)) -> bytes:
    """A small solid-colour JPEG (BGR colour, width x height)."""
    image = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    image[:] = color
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()
