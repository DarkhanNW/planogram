from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import (
    MANAGER,
    OPERATOR,
    VIEWER,
    FakeRecognizer,
    empty,
    register_fixture,
    shelf_row,
    upload_photo,
)
from planogram.recognition import EmptyRegion, Recognition, RecognizedFacing
from test_extraction import stock_catalogue
from test_review import draft_from


def approve_plan(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], *rows: list[Any], bay: int = 1) -> dict[str, Any]:
    draft = draft_from(client, recognizer, fixture, *rows, bay=bay)
    approved: dict[str, Any] = client.post(f"/planograms/{draft['id']}/approve", headers=MANAGER).json()
    return approved


def check(
    client: TestClient,
    recognizer: FakeRecognizer,
    fixture: dict[str, Any],
    facings: list[RecognizedFacing],
    empties: list[EmptyRegion] = [],
    bay: int = 1,
) -> dict[str, Any]:
    recognizer.result = Recognition(facings=facings, empty_regions=empties)
    photo = upload_photo(client, fixture, bay=bay).json()
    response = client.post("/compliance-checks", json={"shelf_photo_id": photo["id"]}, headers=OPERATOR)
    assert response.status_code == 202, response.text
    job = client.get(f"/jobs/{response.json()['id']}", headers=VIEWER).json()
    assert job["status"] == "done", job
    result: dict[str, Any] = client.get(job["result_url"], headers=VIEWER).json()
    return result


def kinds(result: dict[str, Any]) -> list[tuple[str, str | None, int]]:
    """(kind, sku, facings involved) for each Deviation."""
    return [(d["kind"], d["sku"], d["facings"]) for d in result["deviations"]]


@pytest.fixture
def fixture(client: TestClient) -> dict[str, Any]:
    stock_catalogue(client, "A", "B", "C", "X")
    return register_fixture(client)


def test_a_shelf_as_planned_is_fully_compliant(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    plan = approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "B"), shelf_row(2, "C"))

    result = check(client, recognizer, fixture, shelf_row(1, "A", "A", "B") + shelf_row(2, "C"))

    assert result["deviations"] == []
    assert result["compliance_score"] == 1.0
    assert result["planogram_id"] == plan["id"]
    assert (result["fixture_id"], result["bay"]) == (fixture["id"], 1)


def test_empty_planned_space_is_a_gap(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "A", "B", "B"))

    result = check(client, recognizer, fixture, shelf_row(1, "A") + shelf_row(1, "B", "B", start=3), [empty(1, 1, 2)])

    [gap] = result["deviations"]
    assert (gap["kind"], gap["sku"], gap["facings"]) == ("Gap", "A", 2)
    assert gap["planned"] == {"bay": 1, "shelf": 1, "order": 1, "facings": 3}
    assert gap["observed"] == {"bay": 1, "shelf": 1, "order": 1, "facings": 1}
    assert gap["box"] == {"x": 50, "y": 300, "w": 100, "h": 100}
    assert gap["confidence"] == 0.95
    assert result["compliance_score"] == pytest.approx(3 / 5)


def test_a_block_with_no_facings_left_is_a_gap(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B", "B", "C"))

    result = check(client, recognizer, fixture, shelf_row(1, "A") + shelf_row(1, "C", start=3), [empty(1, 1, 2)])

    [gap] = result["deviations"]
    assert (gap["kind"], gap["sku"], gap["facings"]) == ("Gap", "B", 2)
    assert gap["planned"] == {"bay": 1, "shelf": 1, "order": 2, "facings": 2}
    assert gap["observed"] is None
    assert result["compliance_score"] == pytest.approx(2 / 4)


def test_products_not_in_the_planogram_are_unexpected(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A"), shelf_row(2, "B", "B"))

    result = check(client, recognizer, fixture, shelf_row(1, "A", "A", "X") + shelf_row(2, "B", "B", None))

    assert kinds(result) == [("Unexpected", "X", 1), ("Unexpected", None, 1)]
    unexpected = result["deviations"][0]
    assert unexpected["planned"] is None
    assert unexpected["observed"] == {"bay": 1, "shelf": 1, "order": 2, "facings": 1}
    assert unexpected["box"] == {"x": 100, "y": 300, "w": 50, "h": 100}
    assert result["compliance_score"] == 1.0


def test_check_is_bound_to_the_planogram_approved_when_submitted(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    first = approve_plan(client, recognizer, fixture, shelf_row(1, "A"))
    earlier = check(client, recognizer, fixture, shelf_row(1, "A"))
    second = approve_plan(client, recognizer, fixture, shelf_row(1, "B"))

    later = check(client, recognizer, fixture, shelf_row(1, "A"))

    assert client.get(f"/compliance-checks/{earlier['id']}", headers=VIEWER).json()["planogram_id"] == first["id"]
    assert later["planogram_id"] == second["id"]
    assert kinds(later) == [("Unexpected", "A", 1)]


def test_check_needs_an_approved_planogram_for_the_bay(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    photo = upload_photo(client, fixture).json()
    response = client.post("/compliance-checks", json={"shelf_photo_id": photo["id"]}, headers=OPERATOR)
    assert response.status_code == 409

    approve_plan(client, recognizer, fixture, shelf_row(1, "A"), bay=1)
    other_bay = upload_photo(client, fixture, bay=2).json()
    response = client.post("/compliance-checks", json={"shelf_photo_id": other_bay["id"]}, headers=OPERATOR)
    assert response.status_code == 409


def test_matching_tries_the_planned_products_first(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    recognizer.calls.clear()

    check(client, recognizer, fixture, shelf_row(1, "A", "B"))

    assert recognizer.calls == [(["A", "B"], ["C", "X"])]


def test_viewer_cannot_submit_but_everyone_reads_results(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A"))
    photo = upload_photo(client, fixture).json()
    assert client.post("/compliance-checks", json={"shelf_photo_id": photo["id"]}, headers=VIEWER).status_code == 403

    result = check(client, recognizer, fixture, shelf_row(1, "A"))
    for who in (VIEWER, OPERATOR, MANAGER):
        assert client.get(f"/compliance-checks/{result['id']}", headers=who).status_code == 200


def test_an_empty_shelf_is_a_gap_for_each_planned_block(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "B"), shelf_row(2, "C"))

    result = check(client, recognizer, fixture, shelf_row(2, "C"), [empty(1, 0, 3)])

    assert kinds(result) == [("Gap", "A", 2), ("Gap", "B", 1)]
    assert [d["box"]["x"] for d in result["deviations"]] == [0, 100]
    assert result["compliance_score"] == pytest.approx(1 / 4)


def test_empty_space_left_after_a_shift_is_a_gap_for_the_absent_block(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B", "C"))

    result = check(client, recognizer, fixture, shelf_row(1, "A", "C"), [empty(1, 2, 1)])

    assert kinds(result) == [("Gap", "B", 1)]
    assert result["deviations"][0]["box"] == {"x": 100, "y": 300, "w": 50, "h": 100}


def test_each_stretch_of_empty_space_is_its_own_gap(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "A"))

    result = check(client, recognizer, fixture, shelf_row(1, "A", start=1), [empty(1, 0, 1), empty(1, 2, 1)])

    assert kinds(result) == [("Gap", "A", 1), ("Gap", "A", 1)]
    assert [d["box"]["x"] for d in result["deviations"]] == [0, 100]
    assert result["compliance_score"] == pytest.approx(1 / 3)
