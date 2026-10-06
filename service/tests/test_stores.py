import pytest
from fastapi.testclient import TestClient

from conftest import MANAGER, OPERATOR, VIEWER


def test_manager_registers_store_and_fixture_and_anyone_lists_them(client: TestClient) -> None:
    store = client.post("/stores", json={"name": "Kensington"}, headers=MANAGER).json()
    fixture = client.post(
        f"/stores/{store['id']}/fixtures", json={"name": "Drinks", "bay_count": 4}, headers=MANAGER
    )
    assert fixture.status_code == 201

    stores = client.get("/stores", headers=VIEWER).json()
    assert [s["name"] for s in stores] == ["Kensington"]

    fixtures = client.get(f"/stores/{store['id']}/fixtures", headers=OPERATOR).json()
    assert [(f["name"], f["bays"]) for f in fixtures] == [("Drinks", [1, 2, 3, 4])]


@pytest.mark.parametrize("who", [VIEWER, OPERATOR])
def test_only_manager_registers_stores(client: TestClient, who: dict[str, str]) -> None:
    assert client.post("/stores", json={"name": "Kensington"}, headers=who).status_code == 403


@pytest.mark.parametrize("who", [VIEWER, OPERATOR])
def test_only_manager_registers_fixtures(client: TestClient, who: dict[str, str]) -> None:
    store = client.post("/stores", json={"name": "Kensington"}, headers=MANAGER).json()
    response = client.post(
        f"/stores/{store['id']}/fixtures", json={"name": "Drinks", "bay_count": 4}, headers=who
    )
    assert response.status_code == 403


def test_fixture_needs_at_least_one_bay(client: TestClient) -> None:
    store = client.post("/stores", json={"name": "Kensington"}, headers=MANAGER).json()
    response = client.post(
        f"/stores/{store['id']}/fixtures", json={"name": "Drinks", "bay_count": 0}, headers=MANAGER
    )
    assert response.status_code == 422


def test_fixture_in_unknown_store_is_not_found(client: TestClient) -> None:
    response = client.post("/stores/nope/fixtures", json={"name": "Drinks", "bay_count": 4}, headers=MANAGER)
    assert response.status_code == 404


def test_personal_details_are_not_accepted(client: TestClient) -> None:
    response = client.post(
        "/stores", json={"name": "Kensington", "manager_email": "jo@example.com"}, headers=MANAGER
    )
    assert response.status_code == 422
