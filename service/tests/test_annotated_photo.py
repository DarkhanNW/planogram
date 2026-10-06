from typing import Any

import numpy as np
from fastapi.testclient import TestClient

from conftest import MANAGER, OPERATOR, VIEWER, FakeRecognizer, empty, jpeg, shelf_row
from planogram.photos import decode_image
from test_compliance import approve_plan, check, fixture  # noqa: F401  (pytest fixture)

BLACK = jpeg(color=(0, 0, 0), size=(600, 400))


def annotated_check(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], *args: Any) -> dict[str, Any]:
    return check(client, recognizer, fixture, *args, image=BLACK)


def pixel_change(client: TestClient, result: dict[str, Any]) -> np.ndarray:
    """How far each pixel of the Annotated Photo is from the Shelf Photo, averaged over colour."""
    response = client.get(result["annotated_photo_url"], headers=VIEWER)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    annotated = decode_image(response.content).astype(int)
    photo = client.get(f"/shelf-photos/{result['shelf_photo_id']}", headers=VIEWER).json()
    original = decode_image(client.get(photo["image_url"], headers=VIEWER).content).astype(int)
    assert annotated.shape == original.shape
    diff: np.ndarray = np.abs(annotated - original).mean(axis=2)
    return diff


def ring_change(diff: np.ndarray, box: dict[str, int]) -> float:
    """The mean change along the ring of pixels just inside the box."""
    x, y, right, bottom = box["x"], box["y"], box["x"] + box["w"] - 1, box["y"] + box["h"] - 1
    ring = np.concatenate([diff[y, x:right], diff[bottom, x:right], diff[y:bottom, x], diff[y:bottom, right]])
    return float(ring.mean())


def label_width(diff: np.ndarray, box: dict[str, int]) -> int:
    """How far the label above the box runs to the right of the box's left edge."""
    row = diff[box["y"] - 4, box["x"] :]
    unchanged = np.flatnonzero(row < 20)
    return int(unchanged[0]) if len(unchanged) else len(row)


def test_each_deviation_is_drawn_at_its_box_with_a_label(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "A", "B", "B"))

    result = annotated_check(client, recognizer, fixture, shelf_row(1, "A") + shelf_row(1, "B", "B", start=3), [empty(1, 1, 2)])

    [gap] = result["deviations"]
    diff = pixel_change(client, result)
    assert ring_change(diff, gap["box"]) > 60
    assert label_width(diff, gap["box"]) > 10
    assert diff[50:250, 300:].mean() < 5, "nothing is drawn away from the Deviations"


def test_each_label_names_its_deviation_kind(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "B"), shelf_row(3, "C", "C"))

    result = annotated_check(
        client, recognizer, fixture, shelf_row(1, "A", "A") + shelf_row(3, "C", "C", "C"), [empty(1, 2, 1)]
    )

    by_kind = {d["kind"]: d for d in result["deviations"]}
    diff = pixel_change(client, result)
    assert label_width(diff, by_kind["Wrong Facing Count"]["box"]) > 2 * label_width(diff, by_kind["Gap"]["box"])


def test_unverified_areas_are_drawn_lighter_than_deviations(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "A", "B"))

    result = annotated_check(client, recognizer, fixture, shelf_row(1, "A", "A", confidence=0.4), [empty(1, 2, 1)])

    [gap], [unverified] = result["deviations"], result["unverified"]
    diff = pixel_change(client, result)
    assert 5 < ring_change(diff, unverified["box"]) < ring_change(diff, gap["box"]) / 2


def test_a_compliant_bay_has_an_annotated_photo_with_nothing_drawn(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A"))

    result = annotated_check(client, recognizer, fixture, shelf_row(1, "A"))

    assert pixel_change(client, result).mean() < 5


def test_the_annotated_photo_is_stored_with_the_check(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    result = annotated_check(client, recognizer, fixture, shelf_row(1, "A"), [empty(1, 1, 1)])

    again = client.get(f"/compliance-checks/{result['id']}", headers=VIEWER).json()

    assert again["annotated_photo_url"] == f"/compliance-checks/{result['id']}/annotated-photo"
    for who in (VIEWER, OPERATOR, MANAGER):
        assert client.get(again["annotated_photo_url"], headers=who).status_code == 200
    assert client.get("/compliance-checks/nope/annotated-photo", headers=VIEWER).status_code == 404


def test_deleting_the_shelf_photo_deletes_its_annotated_photos(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(1, "A", "B"))
    result = annotated_check(client, recognizer, fixture, shelf_row(1, "A"), [empty(1, 1, 1)])

    assert client.delete(f"/shelf-photos/{result['shelf_photo_id']}", headers=MANAGER).status_code == 204

    kept = client.get(f"/compliance-checks/{result['id']}", headers=VIEWER).json()
    assert kept["annotated_photo_url"] is None
    assert kept["deviations"] == result["deviations"]
    assert client.get(result["annotated_photo_url"], headers=VIEWER).status_code == 404


def test_a_label_with_no_room_above_its_deviation_goes_inside_it(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]
) -> None:
    approve_plan(client, recognizer, fixture, shelf_row(4, "A", "B"))

    result = annotated_check(client, recognizer, fixture, shelf_row(4, "A"), [empty(4, 1, 1)])

    [gap] = result["deviations"]
    box = gap["box"]
    assert box["y"] == 0
    assert pixel_change(client, result)[box["y"] + 6, box["x"] + 4 : box["x"] + 30].mean() > 60
