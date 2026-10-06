from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import MANAGER, VIEWER, FakePersonBlurrer, FakeRecognizer, empty, shelf_row
from planogram.app import create_app
from planogram.jobs import InlineJobRunner
from planogram.settings import Settings
from test_compliance import approve_plan, check
from test_extraction import stock_catalogue

START = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


class Clock:
    """Moves only when told, a day at a time by default."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, days: int = 1) -> datetime:
        self.now += timedelta(days=days)
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(settings: Settings, blurrer: FakePersonBlurrer, recognizer: FakeRecognizer, clock: Clock) -> Iterator[TestClient]:
    app = create_app(settings, blurrer=blurrer, recognizer=recognizer, jobs=InlineJobRunner(), clock=clock)
    with TestClient(app) as c:
        yield c


def add_fixture(client: TestClient, store: dict[str, Any] | None = None, bay_count: int = 2) -> dict[str, Any]:
    store = store or client.post("/stores", json={"name": "Kensington"}, headers=MANAGER).json()
    fixture: dict[str, Any] = client.post(
        f"/stores/{store['id']}/fixtures", json={"name": "Drinks", "bay_count": bay_count}, headers=MANAGER
    ).json()
    return fixture


@pytest.fixture
def fixture(client: TestClient) -> dict[str, Any]:
    stock_catalogue(client, "A", "B", "C")
    return add_fixture(client)


def listed(client: TestClient, **filters: Any) -> list[str]:
    response = client.get("/compliance-checks", params=filters, headers=VIEWER)
    assert response.status_code == 200, response.text
    return [c["id"] for c in response.json()]


# Listing Compliance Checks


def test_checks_are_listed_newest_first_with_their_results(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "B"))
    clock.advance()
    older = check(client, recognizer, fixture, shelf_row(1, "A", "A", "B"))
    clock.advance()
    newer = check(client, recognizer, fixture, shelf_row(1, "A") + shelf_row(1, "B", start=2), [empty(1, 1, 1)])

    [first, second] = client.get("/compliance-checks", headers=VIEWER).json()

    assert (first["id"], second["id"]) == (newer["id"], older["id"])
    assert (first["store_id"], first["fixture_id"], first["bay"]) == (fixture["store_id"], fixture["id"], 1)
    assert first["submitted_at"] == newer["submitted_at"]
    assert first["compliance_score"] == pytest.approx(2 / 3)
    assert first["coverage"] == 1.0
    assert [d["kind"] for d in first["deviations"]] == ["Gap"]


def test_checks_are_filtered_by_store_fixture_and_bay(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    store = {"id": fixture["store_id"]}
    sibling = add_fixture(client, store)
    elsewhere = add_fixture(client)
    for f in (fixture, sibling, elsewhere):
        approve_plan(client, recognizer, f, shelf_row(1, "A"), bay=1)
        approve_plan(client, recognizer, f, shelf_row(1, "B"), bay=2)
    bay1 = check(client, recognizer, fixture, shelf_row(1, "A"), bay=1)["id"]
    bay2 = check(client, recognizer, fixture, shelf_row(1, "B"), bay=2)["id"]
    in_sibling = check(client, recognizer, sibling, shelf_row(1, "A"))["id"]
    in_elsewhere = check(client, recognizer, elsewhere, shelf_row(1, "A"))["id"]

    assert set(listed(client)) == {bay1, bay2, in_sibling, in_elsewhere}
    assert set(listed(client, store_id=fixture["store_id"])) == {bay1, bay2, in_sibling}
    assert set(listed(client, fixture_id=fixture["id"])) == {bay1, bay2}
    assert listed(client, fixture_id=fixture["id"], bay=2) == [bay2]
    assert listed(client, store_id=elsewhere["store_id"], fixture_id=fixture["id"]) == []


def test_checks_are_filtered_by_time_range(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A"))
    first = check(client, recognizer, fixture, shelf_row(1, "A"))["id"]
    clock.advance()
    second = check(client, recognizer, fixture, shelf_row(1, "A"))["id"]
    clock.advance()
    third = check(client, recognizer, fixture, shelf_row(1, "A"))["id"]
    day2 = (START + timedelta(days=1)).isoformat()

    assert listed(client, since=day2) == [third, second]
    assert listed(client, until=day2) == [second, first]
    assert listed(client, since=day2, until=day2) == [second]
    # A time without a zone is UTC.
    assert listed(client, since="2026-09-02T09:00:00") == [third, second]


def test_listing_checks_needs_a_role_and_the_api_key(client: TestClient) -> None:
    assert client.get("/compliance-checks", headers={"X-API-Key": "wrong", "X-User-Id": "u", "X-User-Role": "Viewer"}).status_code == 401
    assert client.get("/compliance-checks", headers=VIEWER).status_code == 200


# Score history


def history(client: TestClient, fixture: dict[str, Any], bay: int | None = None, **filters: Any) -> dict[str, Any]:
    url = f"/fixtures/{fixture['id']}" + (f"/bays/{bay}" if bay is not None else "") + "/score-history"
    response = client.get(url, params=filters, headers=VIEWER)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def scores(result: dict[str, Any]) -> list[tuple[int, float | None, float]]:
    return [(p["bay"], p["compliance_score"], p["coverage"]) for p in result["points"]]


def test_bay_history_shows_score_and_coverage_oldest_first(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    plan = approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "B", "C"))
    clock.advance()
    full = check(client, recognizer, fixture, shelf_row(1, "A", "A", "B", "C"))
    clock.advance()
    gap = check(client, recognizer, fixture, shelf_row(1, "A", "A") + shelf_row(1, "C", start=3), [empty(1, 2, 1)])
    clock.advance()
    unsure = check(client, recognizer, fixture, shelf_row(1, "A", "A", "B") + shelf_row(1, "C", start=3, confidence=0.3))

    result = history(client, fixture, bay=1)

    assert scores(result) == [(1, 1.0, 1.0), (1, 0.75, 1.0), (1, 1.0, 0.75)]
    assert [p["check_id"] for p in result["points"]] == [full["id"], gap["id"], unsure["id"]]
    assert [p["submitted_at"] for p in result["points"]] == [full["submitted_at"], gap["submitted_at"], unsure["submitted_at"]]
    assert {p["planogram_id"] for p in result["points"]} == {plan["id"]}


def test_history_marks_when_the_approved_planogram_changed(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    first = approve_plan(client, recognizer, fixture, shelf_row(1, "A"))
    clock.advance()
    check(client, recognizer, fixture, shelf_row(1, "A"))
    clock.advance()
    second = approve_plan(client, recognizer, fixture, shelf_row(1, "B"))
    clock.advance()
    check(client, recognizer, fixture, shelf_row(1, "B"))

    result = history(client, fixture, bay=1)

    assert result["planogram_changes"] == [
        {"planogram_id": first["id"], "approved_at": first["approved_at"], "bays": [1]},
        {"planogram_id": second["id"], "approved_at": second["approved_at"], "bays": [1]},
    ]
    assert [p["planogram_id"] for p in result["points"]] == [first["id"], second["id"]]


def test_bay_history_marks_only_changes_to_that_bay(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    bay1 = approve_plan(client, recognizer, fixture, shelf_row(1, "A"), bay=1)
    clock.advance()
    bay2 = approve_plan(client, recognizer, fixture, shelf_row(1, "B"), bay=2)
    clock.advance()
    # Re-extracting Bay 1 as it already was approves the same layout for it: no change.
    approve_plan(client, recognizer, fixture, shelf_row(1, "A"), bay=1)

    def changes(bay: int | None = None) -> list[tuple[str, list[int]]]:
        return [(c["planogram_id"], c["bays"]) for c in history(client, fixture, bay=bay)["planogram_changes"]]

    assert changes() == [(bay1["id"], [1]), (bay2["id"], [2])]
    assert changes(bay=1) == [(bay1["id"], [1])]
    assert changes(bay=2) == [(bay2["id"], [2])]


def test_fixture_history_shows_every_bay(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A"), bay=1)
    approve_plan(client, recognizer, fixture, shelf_row(1, "B", "B"), bay=2)
    clock.advance()
    check(client, recognizer, fixture, shelf_row(1, "A", "A"), bay=1)
    clock.advance()
    check(client, recognizer, fixture, shelf_row(1, "B"), [empty(1, 1, 1)], bay=2)
    clock.advance()
    check(client, recognizer, fixture, shelf_row(1, "A"), [empty(1, 1, 1)], bay=1)

    assert scores(history(client, fixture)) == [(1, 1.0, 1.0), (2, 0.5, 1.0), (1, 0.5, 1.0)]
    assert scores(history(client, fixture, bay=2)) == [(2, 0.5, 1.0)]


def test_history_is_limited_to_a_time_range(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    first = approve_plan(client, recognizer, fixture, shelf_row(1, "A"))
    clock.advance()
    check(client, recognizer, fixture, shelf_row(1, "A"))
    clock.advance()
    second = approve_plan(client, recognizer, fixture, shelf_row(1, "B"))
    clock.advance()
    later = check(client, recognizer, fixture, shelf_row(1, "B"))

    result = history(client, fixture, bay=1, since=(START + timedelta(days=2)).isoformat())

    assert [p["check_id"] for p in result["points"]] == [later["id"]]
    assert [c["planogram_id"] for c in result["planogram_changes"]] == [second["id"]]
    assert first["id"] not in [c["planogram_id"] for c in result["planogram_changes"]]


def test_history_of_an_unknown_fixture_or_bay_is_not_found(client: TestClient, fixture: dict[str, Any]) -> None:
    assert client.get("/fixtures/nope/score-history", headers=VIEWER).status_code == 404
    assert client.get("/fixtures/nope/bays/1/score-history", headers=VIEWER).status_code == 404
    assert client.get(f"/fixtures/{fixture['id']}/bays/3/score-history", headers=VIEWER).status_code == 404
    assert history(client, fixture, bay=1) == {"points": [], "planogram_changes": []}
