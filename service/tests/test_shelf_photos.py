from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import MANAGER, OPERATOR, VIEWER, FakePersonBlurrer, register_fixture, upload_photo
from planogram.geometry import Box


def checkerboard(width: int = 400, height: int = 300, square: int = 4) -> np.ndarray:
    ys, xs = np.mgrid[0:height, 0:width]
    pattern = (((xs // square) + (ys // square)) % 2 * 255).astype(np.uint8)
    return cv2.merge([pattern, pattern, pattern])


def png(image: np.ndarray) -> bytes:
    return cv2.imencode(".png", image)[1].tobytes()


def decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image


def sharpness(image: np.ndarray, box: Box) -> float:
    region = cv2.cvtColor(image[box.y : box.y + box.h, box.x : box.x + box.w], cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(region, cv2.CV_64F).var())


PERSON = Box(x=100, y=60, w=120, h=160)
BACKGROUND = Box(x=280, y=20, w=100, h=100)


def test_operator_uploads_a_tagged_shelf_photo(client: TestClient) -> None:
    fixture = register_fixture(client)

    response = upload_photo(client, fixture, bay=2, who=OPERATOR)

    assert response.status_code == 201
    photo = response.json()
    assert (photo["store_id"], photo["fixture_id"], photo["bay"]) == (fixture["store_id"], fixture["id"], 2)
    assert photo["uploaded_by"] == "operator-1"
    assert photo["uploaded_at"]
    assert client.get(f"/shelf-photos/{photo['id']}", headers=VIEWER).json() == photo
    assert client.get(photo["image_url"], headers=VIEWER).status_code == 200


def test_viewer_cannot_upload(client: TestClient) -> None:
    fixture = register_fixture(client)
    assert upload_photo(client, fixture, who=VIEWER).status_code == 403


def test_photo_must_show_a_bay_of_the_fixture(client: TestClient) -> None:
    fixture = register_fixture(client, bay_count=4)
    assert upload_photo(client, fixture, bay=5).status_code == 422
    assert upload_photo(client, {**fixture, "store_id": "other"}).status_code == 422


def test_unreadable_photo_is_rejected(client: TestClient) -> None:
    fixture = register_fixture(client)
    assert upload_photo(client, fixture, image=b"not an image").status_code == 422


def test_people_are_blurred_before_the_photo_is_stored(
    client: TestClient, blurrer: FakePersonBlurrer, tmp_path: Path
) -> None:
    blurrer.people = [PERSON]
    original = checkerboard()
    fixture = register_fixture(client)

    photo = upload_photo(client, fixture, image=png(original)).json()

    stored = decode(client.get(photo["image_url"], headers=VIEWER).content)
    assert sharpness(stored, PERSON) < sharpness(original, PERSON) * 0.05
    assert sharpness(stored, BACKGROUND) > sharpness(original, BACKGROUND) * 0.5

    # Nothing persisted anywhere holds the unblurred person.
    for path in tmp_path.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        assert png(original) not in data
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is not None and image.shape == original.shape:
            assert sharpness(image, PERSON) < sharpness(original, PERSON) * 0.05


def test_manager_deletes_a_shelf_photo(client: TestClient) -> None:
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()

    assert client.delete(f"/shelf-photos/{photo['id']}", headers=MANAGER).status_code == 204

    assert client.get(photo["image_url"], headers=VIEWER).status_code == 404


@pytest.mark.parametrize("who", [VIEWER, OPERATOR])
def test_only_manager_deletes_shelf_photos(client: TestClient, who: dict[str, str]) -> None:
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()

    assert client.delete(f"/shelf-photos/{photo['id']}", headers=who).status_code == 403
    assert client.get(photo["image_url"], headers=VIEWER).status_code == 200
