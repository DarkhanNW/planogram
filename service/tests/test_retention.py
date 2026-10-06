from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import MANAGER, VIEWER, FakePersonBlurrer, FakeRecognizer, empty, register_fixture, shelf_row, upload_photo
from planogram.app import create_app
from planogram.context import Context
from planogram.jobs import InlineJobRunner
from planogram.retention import months_before, sweep_expired_shelf_photos
from planogram.settings import Settings
from test_compliance import approve_plan, check
from test_extraction import stock_catalogue
from test_history import Clock, client, clock  # noqa: F401  (pytest fixtures)

SIX_MONTHS = 181
"""Days from the test clock's start (1 September) to six months later (1 March)."""


def app(settings: Settings, blurrer: FakePersonBlurrer, recognizer: FakeRecognizer, clock: Clock) -> FastAPI:
    return create_app(settings, blurrer=blurrer, recognizer=recognizer, jobs=InlineJobRunner(), clock=clock)


@pytest.fixture
def fixture(client: TestClient) -> dict[str, Any]:
    stock_catalogue(client, "A", "B")
    return register_fixture(client)


def context(client: TestClient) -> Context:
    ctx: Context = client.app.state.context  # type: ignore[attr-defined]
    return ctx


def photo(client: TestClient, photo_id: str) -> dict[str, Any]:
    response = client.get(f"/shelf-photos/{photo_id}", headers=VIEWER)
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


def gap_check(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> dict[str, Any]:
    return check(client, recognizer, fixture, shelf_row(1, "A"), [empty(1, 1, 1)])


# The retention sweep


def test_the_sweep_deletes_shelf_photos_six_months_old(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    plan = approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    old = gap_check(client, recognizer, fixture)
    clock.advance(SIX_MONTHS - 1)
    recent = gap_check(client, recognizer, fixture)
    clock.advance()

    sweep_expired_shelf_photos(context(client))

    for photo_id in (old["shelf_photo_id"], plan["bays"][0]["shelf_photo_id"]):
        assert photo(client, photo_id)["image_url"] is None
        assert client.get(f"/shelf-photos/{photo_id}/image", headers=VIEWER).status_code == 404
    assert client.get(old["annotated_photo_url"], headers=VIEWER).status_code == 404
    assert photo(client, recent["shelf_photo_id"])["image_url"] is not None
    assert client.get(recent["annotated_photo_url"], headers=VIEWER).status_code == 200


def test_results_stay_readable_after_the_sweep(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], clock: Clock
) -> None:
    plan = approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    result = gap_check(client, recognizer, fixture)
    clock.advance(SIX_MONTHS)

    sweep_expired_shelf_photos(context(client))

    kept = client.get(f"/compliance-checks/{result['id']}", headers=VIEWER).json()
    assert kept["annotated_photo_url"] is None
    assert {k: v for k, v in kept.items() if k != "annotated_photo_url"} == {
        k: v for k, v in result.items() if k != "annotated_photo_url"
    }
    assert client.get(f"/planograms/{plan['id']}", headers=VIEWER).json() == plan
    [listed] = client.get("/compliance-checks", headers=VIEWER).json()
    assert (listed["compliance_score"], listed["coverage"]) == (result["compliance_score"], result["coverage"])


def test_the_retention_period_is_configurable(
    settings: Settings, blurrer: FakePersonBlurrer, recognizer: FakeRecognizer, clock: Clock
) -> None:
    with TestClient(app(replace(settings, photo_retention_months=1), blurrer, recognizer, clock)) as client:
        uploaded = upload_photo(client, register_fixture(client)).json()
        clock.advance(29)
        sweep_expired_shelf_photos(context(client))
        assert photo(client, uploaded["id"])["image_url"] is not None

        clock.advance(1)
        sweep_expired_shelf_photos(context(client))
        assert photo(client, uploaded["id"])["image_url"] is None


def test_the_service_sweeps_when_it_starts(
    settings: Settings, blurrer: FakePersonBlurrer, recognizer: FakeRecognizer, clock: Clock
) -> None:
    with TestClient(app(settings, blurrer, recognizer, clock)) as client:
        uploaded = upload_photo(client, register_fixture(client)).json()
    clock.advance(SIX_MONTHS)

    with TestClient(app(settings, blurrer, recognizer, clock)) as client:
        assert photo(client, uploaded["id"])["image_url"] is None


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (datetime(2026, 9, 1, 9, tzinfo=UTC), 6, datetime(2026, 3, 1, 9, tzinfo=UTC)),
        (datetime(2026, 8, 31, tzinfo=UTC), 6, datetime(2026, 2, 28, tzinfo=UTC)),
        (datetime(2027, 1, 15, tzinfo=UTC), 13, datetime(2025, 12, 15, tzinfo=UTC)),
    ],
)
def test_months_before_counts_calendar_months(start: datetime, months: int, expected: datetime) -> None:
    assert months_before(start, months) == expected


# A Manager deleting a Shelf Photo


def test_results_stay_readable_after_a_manager_deletes_the_photo(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    plan = approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    result = gap_check(client, recognizer, fixture)

    assert client.delete(f"/shelf-photos/{result['shelf_photo_id']}", headers=MANAGER).status_code == 204

    kept = client.get(f"/compliance-checks/{result['id']}", headers=VIEWER).json()
    assert (kept["compliance_score"], kept["coverage"], kept["deviations"]) == (
        result["compliance_score"], result["coverage"], result["deviations"]
    )
    assert client.get(result["annotated_photo_url"], headers=VIEWER).status_code == 404
    assert client.get(f"/planograms/{plan['id']}", headers=VIEWER).json() == plan


def test_a_shelf_photo_names_the_approved_planogram_extracted_from_it(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    first = approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    first_photo = first["bays"][0]["shelf_photo_id"]
    assert photo(client, first_photo)["approved_planogram_id"] == first["id"]

    second = approve_plan(client, recognizer, fixture, shelf_row(1, "B", "A"))

    assert photo(client, first_photo)["approved_planogram_id"] is None, "a Superseded Planogram needs no warning"
    listed = {p["id"]: p for p in client.get(f"/shelf-photos?fixture_id={fixture['id']}", headers=VIEWER).json()}
    assert listed[second["bays"][0]["shelf_photo_id"]]["approved_planogram_id"] == second["id"]


def test_deleting_the_photo_behind_an_approved_planogram_needs_confirming(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    plan = approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    photo_id = plan["bays"][0]["shelf_photo_id"]

    refused = client.delete(f"/shelf-photos/{photo_id}", headers=MANAGER)
    assert refused.status_code == 409
    assert refused.json()["approved_planogram_id"] == plan["id"]
    assert photo(client, photo_id)["image_url"] is not None

    assert client.delete(f"/shelf-photos/{photo_id}?confirm=true", headers=MANAGER).status_code == 204
    assert photo(client, photo_id)["image_url"] is None
    assert client.get(f"/planograms/{plan['id']}", headers=VIEWER).json() == plan
