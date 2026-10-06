from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import MANAGER, OPERATOR, VIEWER, FakeRecognizer, register_fixture, shelf_row, upload_photo
from planogram.recognition import Recognition
from test_extraction import extract, stock_catalogue, summary


def draft_from(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], *rows: list[Any], bay: int = 1) -> dict[str, Any]:
    recognizer.result = Recognition(facings=[f for row in rows for f in row], empty_regions=[])
    job = extract(client, upload_photo(client, fixture, bay=bay).json()["id"])
    planogram: dict[str, Any] = client.get(job["result_url"], headers=VIEWER).json()
    return planogram


def block_ids(planogram: dict[str, Any], bay: int = 1, shelf: int = 1) -> list[str]:
    layout = next(b for b in planogram["bays"] if b["bay"] == bay)
    return [b["id"] for b in next(s for s in layout["shelves"] if s["number"] == shelf)["blocks"]]


def blocks_url(planogram: dict[str, Any], bay: int = 1) -> str:
    return f"/planograms/{planogram['id']}/bays/{bay}"


@pytest.fixture
def fixture(client: TestClient) -> dict[str, Any]:
    stock_catalogue(client, "A", "B", "C")
    return register_fixture(client)


def test_manager_changes_a_blocks_product_and_facing_count(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A", None, "B"))
    _, unknown, b = block_ids(draft)

    client.patch(f"{blocks_url(draft)}/blocks/{unknown}", json={"sku": "C"}, headers=MANAGER)
    response = client.patch(f"{blocks_url(draft)}/blocks/{b}", json={"facings": 3}, headers=MANAGER)

    assert response.status_code == 200
    assert summary(response.json()["bays"][0]) == [[("A", 1), ("C", 1), ("B", 3)]]


def test_a_block_cannot_become_a_product_missing_from_the_catalogue(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, None))
    [unknown] = block_ids(draft)
    response = client.patch(f"{blocks_url(draft)}/blocks/{unknown}", json={"sku": "NOPE"}, headers=MANAGER)
    assert response.status_code == 422


def test_facing_count_must_be_positive(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A"))
    [a] = block_ids(draft)
    assert client.patch(f"{blocks_url(draft)}/blocks/{a}", json={"facings": 0}, headers=MANAGER).status_code == 422


def test_blocks_of_the_same_product_side_by_side_become_one_block(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A", "A", None, "B"))
    _, unknown, _ = block_ids(draft)

    edited = client.patch(f"{blocks_url(draft)}/blocks/{unknown}", json={"sku": "A"}, headers=MANAGER).json()

    assert summary(edited["bays"][0]) == [[("A", 3), ("B", 1)]]
    assert edited["bays"][0]["shelves"][0]["blocks"][0]["box"] == {"x": 0, "y": 300, "w": 150, "h": 100}


def test_manager_deletes_a_block(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A", "B", "C"))
    _, b, _ = block_ids(draft)

    response = client.delete(f"{blocks_url(draft)}/blocks/{b}", headers=MANAGER)

    assert summary(response.json()["bays"][0]) == [[("A", 1), ("C", 1)]]


def test_manager_inserts_a_block_at_a_chosen_place_on_a_shelf(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A", "C"), shelf_row(2, "A"))

    response = client.post(
        f"{blocks_url(draft)}/shelves/1/blocks", json={"sku": "B", "facings": 2, "position": 1}, headers=MANAGER
    )

    assert response.status_code == 201
    assert summary(response.json()["bays"][0]) == [[("A", 1), ("B", 2), ("C", 1)], [("A", 1)]]


def test_inserting_onto_a_new_shelf_adds_the_shelf(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A"))

    response = client.post(f"{blocks_url(draft)}/shelves/2/blocks", json={"sku": "B", "facings": 1, "position": 0}, headers=MANAGER)

    assert summary(response.json()["bays"][0]) == [[("A", 1)], [("B", 1)]]


@pytest.mark.parametrize("who", [VIEWER, OPERATOR])
def test_only_manager_edits_drafts(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], who: dict[str, str]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A"))
    [a] = block_ids(draft)
    url = blocks_url(draft)
    assert client.patch(f"{url}/blocks/{a}", json={"facings": 2}, headers=who).status_code == 403
    assert client.delete(f"{url}/blocks/{a}", headers=who).status_code == 403
    assert client.post(f"{url}/shelves/1/blocks", json={"sku": "B", "facings": 1, "position": 0}, headers=who).status_code == 403
    assert client.post(f"/planograms/{draft['id']}/approve", headers=who).status_code == 403


def test_approval_is_refused_while_unknown_products_remain(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A", None), shelf_row(2, None, "B"))

    response = client.post(f"/planograms/{draft['id']}/approve", headers=MANAGER)

    assert response.status_code == 409
    assert [(u["bay"], u["shelf"], u["position"]) for u in response.json()["unknown_blocks"]] == [(1, 1, 1), (1, 2, 0)]
    assert client.get(f"/planograms/{draft['id']}", headers=VIEWER).json()["status"] == "Draft"


def test_approval_records_the_approver_and_time(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    draft = draft_from(client, recognizer, fixture, shelf_row(1, "A"))

    approved = client.post(f"/planograms/{draft['id']}/approve", headers=MANAGER).json()

    assert approved["status"] == "Approved"
    assert approved["approved_by"] == "manager-1"
    assert approved["approved_at"]


def test_approving_supersedes_the_previous_approved_planogram(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    first = draft_from(client, recognizer, fixture, shelf_row(1, "A"))
    client.post(f"/planograms/{first['id']}/approve", headers=MANAGER)
    second = draft_from(client, recognizer, fixture, shelf_row(1, "B"))
    assert second["id"] != first["id"]

    client.post(f"/planograms/{second['id']}/approve", headers=MANAGER)

    history = client.get(f"/fixtures/{fixture['id']}/planograms", headers=VIEWER).json()
    assert [(p["id"], p["status"]) for p in history] == [(second["id"], "Approved"), (first["id"], "Superseded")]
    superseded = client.get(f"/planograms/{first['id']}", headers=VIEWER).json()
    assert superseded["superseded_at"]
    assert summary(superseded["bays"][0]) == [[("A", 1)]]


def test_a_new_draft_keeps_the_approved_layout_of_bays_not_re_extracted(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    first = draft_from(client, recognizer, fixture, shelf_row(1, "A"), bay=1)
    draft_from(client, recognizer, fixture, shelf_row(1, "B"), bay=2)
    client.post(f"/planograms/{first['id']}/approve", headers=MANAGER)

    second = draft_from(client, recognizer, fixture, shelf_row(1, "C"), bay=2)

    assert [(b["bay"], summary(b)) for b in second["bays"]] == [(1, [[("A", 1)]]), (2, [[("C", 1)]])]


@pytest.mark.parametrize("status", ["Approved", "Superseded"])
def test_approved_and_superseded_planograms_cannot_be_edited(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], status: str
) -> None:
    first = draft_from(client, recognizer, fixture, shelf_row(1, "A"))
    client.post(f"/planograms/{first['id']}/approve", headers=MANAGER)
    if status == "Superseded":
        second = draft_from(client, recognizer, fixture, shelf_row(1, "B"))
        client.post(f"/planograms/{second['id']}/approve", headers=MANAGER)
    [a] = block_ids(first)
    url = blocks_url(first)

    assert client.patch(f"{url}/blocks/{a}", json={"facings": 2}, headers=MANAGER).status_code == 409
    assert client.delete(f"{url}/blocks/{a}", headers=MANAGER).status_code == 409
    assert client.post(f"{url}/shelves/1/blocks", json={"sku": "B", "facings": 1, "position": 0}, headers=MANAGER).status_code == 409
    assert client.post(f"/planograms/{first['id']}/approve", headers=MANAGER).status_code == 409
    assert client.get(f"/planograms/{first['id']}", headers=VIEWER).json()["status"] == status
