from typing import Any

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import MANAGER, OPERATOR, VIEWER, FakeRecognizer, register_fixture, shelf_row
from test_extraction import stock_catalogue, summary
from test_review import block_ids, blocks_url, draft_from


def image_size(data: bytes) -> tuple[int, int]:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return image.shape[1], image.shape[0]


@pytest.fixture
def draft(client: TestClient, recognizer: FakeRecognizer) -> dict[str, Any]:
    stock_catalogue(client, "A")
    fixture = register_fixture(client)
    # Two Facings of an Unknown Product: one 50x100 Block box per Facing.
    return draft_from(client, recognizer, fixture, shelf_row(1, "A", None, None))


def resolve_url(draft: dict[str, Any], block_id: str) -> str:
    return f"{blocks_url(draft)}/blocks/{block_id}/resolve"


def test_unknown_products_crop_is_viewable(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown = block_ids(draft)
    crop = client.get(f"{blocks_url(draft)}/blocks/{unknown}/crop", headers=VIEWER)
    assert crop.status_code == 200
    assert image_size(crop.content) == (100, 100)


def test_manager_creates_a_product_from_an_unknown_products_crop(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown = block_ids(draft)

    response = client.post(resolve_url(draft, unknown), json={"new_product": {"sku": "N", "name": "Aloe Vera Green"}}, headers=MANAGER)

    assert response.status_code == 200
    assert summary(response.json()["bays"][0]) == [[("A", 1), ("N", 2)]]
    product = client.get("/products/N", headers=VIEWER).json()
    assert product["name"] == "Aloe Vera Green"
    [reference] = product["reference_images"]
    # The reference image is one Facing of the Block.
    assert image_size(client.get(reference["url"], headers=VIEWER).content) == (50, 100)


def test_manager_adds_the_crop_to_an_existing_product(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown = block_ids(draft)

    response = client.post(resolve_url(draft, unknown), json={"existing_sku": "A"}, headers=MANAGER)

    assert summary(response.json()["bays"][0]) == [[("A", 3)]]
    assert len(client.get("/products/A", headers=VIEWER).json()["reference_images"]) == 2


def test_new_product_needs_an_unused_sku(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown = block_ids(draft)
    response = client.post(resolve_url(draft, unknown), json={"new_product": {"sku": "A", "name": "Dup"}}, headers=MANAGER)
    assert response.status_code == 409


def test_existing_product_must_be_in_the_catalogue(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown = block_ids(draft)
    assert client.post(resolve_url(draft, unknown), json={"existing_sku": "NOPE"}, headers=MANAGER).status_code == 422


def test_exactly_one_resolution_is_given(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown = block_ids(draft)
    both = {"existing_sku": "A", "new_product": {"sku": "N", "name": "New"}}
    assert client.post(resolve_url(draft, unknown), json=both, headers=MANAGER).status_code == 422
    assert client.post(resolve_url(draft, unknown), json={}, headers=MANAGER).status_code == 422


def test_only_unknown_products_are_resolved(client: TestClient, draft: dict[str, Any]) -> None:
    known, _ = block_ids(draft)
    assert client.post(resolve_url(draft, known), json={"existing_sku": "A"}, headers=MANAGER).status_code == 409


@pytest.mark.parametrize("who", [VIEWER, OPERATOR])
def test_only_manager_resolves(client: TestClient, draft: dict[str, Any], who: dict[str, str]) -> None:
    _, unknown = block_ids(draft)
    assert client.post(resolve_url(draft, unknown), json={"existing_sku": "A"}, headers=who).status_code == 403
    response = client.post(resolve_url(draft, unknown), json={"new_product": {"sku": "N", "name": "New"}}, headers=who)
    assert response.status_code == 403
    assert client.get("/products/N", headers=VIEWER).status_code == 404


def test_resolving_then_approving(client: TestClient, draft: dict[str, Any]) -> None:
    _, unknown = block_ids(draft)
    client.post(resolve_url(draft, unknown), json={"new_product": {"sku": "N", "name": "New"}}, headers=MANAGER)
    assert client.post(f"/planograms/{draft['id']}/approve", headers=MANAGER).json()["status"] == "Approved"
