from typing import Any

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import FACING_WIDTH, MANAGER, OPERATOR, SHELF_HEIGHT, VIEWER, FakeRecognizer, register_fixture, shelf_row
from test_extraction import stock_catalogue, summary
from test_review import block_ids, blocks_url, draft_from

# BGR colour of each Facing column on the Shelf Photo, from the left.
COLUMNS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]


def decode(data: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def image_size(data: bytes) -> tuple[int, int]:
    image = decode(data)
    return image.shape[1], image.shape[0]


def facing_shown(data: bytes) -> int:
    """Which Facing of the striped Shelf Photo, counted from the left, an image shows."""
    mean = decode(data).reshape(-1, 3).mean(axis=0)
    return int(np.argmin([np.linalg.norm(mean - np.array(bgr)) for bgr in COLUMNS]))


def striped_photo() -> bytes:
    image = np.zeros((4 * SHELF_HEIGHT, len(COLUMNS) * FACING_WIDTH, 3), dtype=np.uint8)
    for i, bgr in enumerate(COLUMNS):
        image[:, i * FACING_WIDTH:(i + 1) * FACING_WIDTH] = bgr
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


@pytest.fixture
def draft(client: TestClient, recognizer: FakeRecognizer) -> dict[str, Any]:
    stock_catalogue(client, "A")
    fixture = register_fixture(client)
    # A known Facing, then two Facings the Recognizer cannot match: one Block each.
    return draft_from(client, recognizer, fixture, shelf_row(1, "A", None, None), image=striped_photo())


def resolve_url(draft: dict[str, Any], block_id: str) -> str:
    return f"{blocks_url(draft)}/blocks/{block_id}/resolve"


def test_unknown_products_crop_is_viewable(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown, _ = block_ids(draft)
    crop = client.get(f"{blocks_url(draft)}/blocks/{unknown}/crop", headers=VIEWER)
    assert crop.status_code == 200
    assert image_size(crop.content) == (50, 100)


def test_manager_creates_a_product_from_an_unknown_products_crop(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown, _ = block_ids(draft)

    response = client.post(resolve_url(draft, unknown), json={"new_product": {"sku": "N", "name": "Aloe Vera Green"}}, headers=MANAGER)

    assert response.status_code == 200
    assert summary(response.json()["bays"][0]) == [[("A", 1), ("N", 1), (None, 1)]]
    product = client.get("/products/N", headers=VIEWER).json()
    assert product["name"] == "Aloe Vera Green"
    [reference] = product["reference_images"]
    assert image_size(client.get(reference["url"], headers=VIEWER).content) == (50, 100)


def test_manager_adds_the_crop_to_an_existing_product(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown, _ = block_ids(draft)

    response = client.post(resolve_url(draft, unknown), json={"existing_sku": "A"}, headers=MANAGER)

    assert summary(response.json()["bays"][0]) == [[("A", 2), (None, 1)]]
    assert len(client.get("/products/A", headers=VIEWER).json()["reference_images"]) == 2


def test_new_product_needs_an_unused_sku(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown, _ = block_ids(draft)
    response = client.post(resolve_url(draft, unknown), json={"new_product": {"sku": "A", "name": "Dup"}}, headers=MANAGER)
    assert response.status_code == 409


def test_existing_product_must_be_in_the_catalogue(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown, _ = block_ids(draft)
    assert client.post(resolve_url(draft, unknown), json={"existing_sku": "NOPE"}, headers=MANAGER).status_code == 422


def test_exactly_one_resolution_is_given(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown, _ = block_ids(draft)
    both = {"existing_sku": "A", "new_product": {"sku": "N", "name": "New"}}
    assert client.post(resolve_url(draft, unknown), json=both, headers=MANAGER).status_code == 422
    assert client.post(resolve_url(draft, unknown), json={}, headers=MANAGER).status_code == 422


def test_only_unknown_products_are_resolved(client: TestClient, draft: dict[str, Any]) -> None:
    known, _, _ = block_ids(draft)
    assert client.post(resolve_url(draft, known), json={"existing_sku": "A"}, headers=MANAGER).status_code == 409


@pytest.mark.parametrize("who", [VIEWER, OPERATOR])
def test_only_manager_resolves(client: TestClient, draft: dict[str, Any], who: dict[str, str]) -> None:
    _, unknown, _ = block_ids(draft)
    assert client.post(resolve_url(draft, unknown), json={"existing_sku": "A"}, headers=who).status_code == 403
    response = client.post(resolve_url(draft, unknown), json={"new_product": {"sku": "N", "name": "New"}}, headers=who)
    assert response.status_code == 403
    assert client.get("/products/N", headers=VIEWER).status_code == 404


def test_the_crop_is_that_facings_box(client: TestClient, draft: dict[str, Any]) -> None:
    _, _, second = block_ids(draft)

    client.post(resolve_url(draft, second), json={"new_product": {"sku": "N", "name": "New"}}, headers=MANAGER)

    [reference] = client.get("/products/N", headers=VIEWER).json()["reference_images"]
    assert facing_shown(client.get(reference["url"], headers=VIEWER).content) == 2


def test_resolving_both_unknown_products_to_one_product_joins_them(client: TestClient, draft: dict[str, Any]) -> None:
    _, first, second = block_ids(draft)
    client.post(resolve_url(draft, first), json={"new_product": {"sku": "N", "name": "New"}}, headers=MANAGER)

    response = client.post(resolve_url(draft, second), json={"existing_sku": "N"}, headers=MANAGER)

    assert summary(response.json()["bays"][0]) == [[("A", 1), ("N", 2)]]
    [_, joined] = response.json()["bays"][0]["shelves"][0]["blocks"]
    assert joined["box"] == {"x": 50, "y": 300, "w": 100, "h": 100}
    assert len(client.get("/products/N", headers=VIEWER).json()["reference_images"]) == 2


def test_resolving_then_approving(client: TestClient, draft: dict[str, Any]) -> None:
    _, first, second = block_ids(draft)
    client.post(resolve_url(draft, first), json={"new_product": {"sku": "N", "name": "New"}}, headers=MANAGER)
    client.post(resolve_url(draft, second), json={"existing_sku": "A"}, headers=MANAGER)
    assert client.post(f"/planograms/{draft['id']}/approve", headers=MANAGER).json()["status"] == "Approved"
