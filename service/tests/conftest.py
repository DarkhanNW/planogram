from pathlib import Path
from typing import Callable, Iterator

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from planogram.app import create_app
from planogram.geometry import Box
from planogram.jobs import InlineJobRunner
from planogram.models import Product
from planogram.recognition import EmptyRegion, RecognizedFacing, Recognition
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


class FakePersonBlurrer:
    """Reports the scripted person boxes for every photo."""

    def __init__(self) -> None:
        self.people: list[Box] = []

    def find_people(self, image: np.ndarray) -> list[Box]:
        return list(self.people)


@pytest.fixture
def blurrer() -> FakePersonBlurrer:
    return FakePersonBlurrer()


class FakeRecognizer:
    """Returns the scripted Recognition for every photo; set ``result`` before submitting.
    ``while_recognizing``, if set, runs once mid-recognition, to interleave requests with a job."""

    def __init__(self) -> None:
        self.result = Recognition(facings=[], empty_regions=[])
        self.error: Exception | None = None
        self.calls: list[tuple[list[str], list[str]]] = []
        self.while_recognizing: Callable[[], None] | None = None

    def recognize(self, image: np.ndarray, candidates: list[Product], fallback: list[Product]) -> Recognition:
        self.calls.append(([p.sku for p in candidates], [p.sku for p in fallback]))
        if self.while_recognizing:
            interleave, self.while_recognizing = self.while_recognizing, None
            interleave()
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def recognizer() -> FakeRecognizer:
    return FakeRecognizer()


@pytest.fixture
def client(settings: Settings, blurrer: FakePersonBlurrer, recognizer: FakeRecognizer) -> Iterator[TestClient]:
    app = create_app(settings, blurrer=blurrer, recognizer=recognizer, jobs=InlineJobRunner())
    with TestClient(app) as c:
        yield c


FACING_WIDTH = 50
SHELF_HEIGHT = 100


def shelf_row(shelf: int, *skus: str | None, confidence: float = 0.95, start: int = 0) -> list[RecognizedFacing]:
    """Facings side by side on a Shelf (counted from the bottom of a 4-Shelf Bay), left to right.
    ``None`` is a Facing the Recognizer could not match: an Unknown Product."""
    top = (4 - shelf) * SHELF_HEIGHT
    return [
        RecognizedFacing(
            sku=sku, shelf=shelf, confidence=confidence,
            box=Box(x=(start + i) * FACING_WIDTH, y=top, w=FACING_WIDTH, h=SHELF_HEIGHT),
        )
        for i, sku in enumerate(skus)
    ]


def empty(shelf: int, start: int, facings: int, confidence: float = 0.95) -> EmptyRegion:
    top = (4 - shelf) * SHELF_HEIGHT
    return EmptyRegion(
        shelf=shelf, confidence=confidence,
        box=Box(x=start * FACING_WIDTH, y=top, w=facings * FACING_WIDTH, h=SHELF_HEIGHT),
    )


def register_fixture(client: TestClient, bay_count: int = 4) -> dict[str, str]:
    store = client.post("/stores", json={"name": "Kensington"}, headers=MANAGER).json()
    return client.post(
        f"/stores/{store['id']}/fixtures", json={"name": "Drinks", "bay_count": bay_count}, headers=MANAGER
    ).json()


def upload_photo(
    client: TestClient, fixture: dict[str, str], bay: int = 1, image: bytes | None = None, who: dict[str, str] = OPERATOR
) -> httpx.Response:
    return client.post(
        "/shelf-photos",
        data={"store_id": fixture["store_id"], "fixture_id": fixture["id"], "bay": str(bay)},
        files={"image": ("bay.jpg", image or jpeg(size=(600, 400)), "image/jpeg")},
        headers=who,
    )


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
