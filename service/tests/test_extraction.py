from typing import Any

from fastapi.testclient import TestClient

from conftest import (
    MANAGER,
    OPERATOR,
    VIEWER,
    FakeRecognizer,
    import_catalogue,
    jpeg,
    register_fixture,
    shelf_row,
    upload_photo,
)
from planogram.recognition import Recognition


def stock_catalogue(client: TestClient, *skus: str) -> None:
    rows = "".join(f"{sku},Product {sku},{sku}.jpg\n" for sku in skus)
    import_catalogue(client, "sku,name,images\n" + rows, {f"{sku}.jpg": jpeg() for sku in skus})


def extract(client: TestClient, photo_id: str, who: dict[str, str] = OPERATOR) -> dict[str, Any]:
    response = client.post("/extractions", json={"shelf_photo_id": photo_id}, headers=who)
    assert response.status_code == 202, response.text
    job: dict[str, Any] = client.get(f"/jobs/{response.json()['id']}", headers=VIEWER).json()
    return job


def summary(bay: dict[str, Any]) -> list[list[tuple[str | None, int]]]:
    """Each Shelf from the bottom as (sku, facings) Blocks from the left."""
    return [[(b["sku"], b["facings"]) for b in shelf["blocks"]] for shelf in bay["shelves"]]


def test_extraction_builds_a_draft_planogram_for_the_photographed_bay(
    client: TestClient, recognizer: FakeRecognizer
) -> None:
    stock_catalogue(client, "A", "B", "C")
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture, bay=2).json()
    # Facings arrive in no particular order; Shelf 1 is the bottom Shelf.
    facings = shelf_row(2, "C", None, None) + shelf_row(1, "A", "A", "B")
    recognizer.result = Recognition(facings=list(reversed(facings)), empty_regions=[])

    job = extract(client, photo["id"])

    assert job["status"] == "done"
    planogram = client.get(job["result_url"], headers=VIEWER).json()
    assert planogram["status"] == "Draft"
    assert planogram["fixture_id"] == fixture["id"]
    [bay] = planogram["bays"]
    assert bay["bay"] == 2
    assert bay["shelf_photo_id"] == photo["id"]
    assert summary(bay) == [[("A", 2), ("B", 1)], [("C", 1), (None, 1), (None, 1)]]
    assert [s["number"] for s in bay["shelves"]] == [1, 2]


def test_blocks_keep_their_box_in_the_source_photo(client: TestClient, recognizer: FakeRecognizer) -> None:
    stock_catalogue(client, "A", "B")
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()
    recognizer.result = Recognition(facings=shelf_row(1, "A", "A", "B"), empty_regions=[])

    planogram = client.get(extract(client, photo["id"])["result_url"], headers=VIEWER).json()

    [shelf] = planogram["bays"][0]["shelves"]
    assert [b["box"] for b in shelf["blocks"]] == [
        {"x": 0, "y": 300, "w": 100, "h": 100},
        {"x": 100, "y": 300, "w": 50, "h": 100},
    ]


def test_unmatched_facings_become_unknown_product_blocks(client: TestClient, recognizer: FakeRecognizer) -> None:
    stock_catalogue(client, "A")
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()
    recognizer.result = Recognition(facings=shelf_row(1, "A", None, "A"), empty_regions=[])

    planogram = client.get(extract(client, photo["id"])["result_url"], headers=VIEWER).json()

    blocks = planogram["bays"][0]["shelves"][0]["blocks"]
    assert [(b["sku"], b["facings"], b["unknown"]) for b in blocks] == [
        ("A", 1, False), (None, 1, True), ("A", 1, False)
    ]


def test_each_unknown_product_facing_is_its_own_block(client: TestClient, recognizer: FakeRecognizer) -> None:
    # Nothing says two unmatched packs side by side are the same Product.
    stock_catalogue(client, "A")
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()
    recognizer.result = Recognition(facings=shelf_row(1, None, None), empty_regions=[])

    planogram = client.get(extract(client, photo["id"])["result_url"], headers=VIEWER).json()

    blocks = planogram["bays"][0]["shelves"][0]["blocks"]
    assert [(b["sku"], b["facings"], b["unknown"], b["box"]) for b in blocks] == [
        (None, 1, True, {"x": 0, "y": 300, "w": 50, "h": 100}),
        (None, 1, True, {"x": 50, "y": 300, "w": 50, "h": 100}),
    ]


def test_extraction_matches_against_the_whole_catalogue(client: TestClient, recognizer: FakeRecognizer) -> None:
    stock_catalogue(client, "A", "B", "C")
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()

    extract(client, photo["id"])

    assert recognizer.calls == [(["A", "B", "C"], [])]


def test_job_reports_failure(client: TestClient, recognizer: FakeRecognizer) -> None:
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()
    recognizer.error = RuntimeError("model crashed")

    job = extract(client, photo["id"])

    assert job["status"] == "failed"
    assert job["result_url"] is None
    assert "model crashed" in job["error"]


def test_viewer_cannot_submit_extraction(client: TestClient) -> None:
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()
    response = client.post("/extractions", json={"shelf_photo_id": photo["id"]}, headers=VIEWER)
    assert response.status_code == 403


def test_extraction_needs_a_photo_with_its_image(client: TestClient) -> None:
    fixture = register_fixture(client)
    photo = upload_photo(client, fixture).json()
    client.delete(f"/shelf-photos/{photo['id']}", headers=MANAGER)

    assert client.post("/extractions", json={"shelf_photo_id": photo["id"]}, headers=OPERATOR).status_code == 409
    assert client.post("/extractions", json={"shelf_photo_id": "nope"}, headers=OPERATOR).status_code == 404


def test_extracting_another_bay_adds_it_to_the_open_draft(client: TestClient, recognizer: FakeRecognizer) -> None:
    stock_catalogue(client, "A", "B")
    fixture = register_fixture(client)
    recognizer.result = Recognition(facings=shelf_row(1, "A"), empty_regions=[])
    first = extract(client, upload_photo(client, fixture, bay=1).json()["id"])
    recognizer.result = Recognition(facings=shelf_row(1, "B"), empty_regions=[])
    second = extract(client, upload_photo(client, fixture, bay=2).json()["id"])

    assert first["result_url"] == second["result_url"]
    planogram = client.get(second["result_url"], headers=VIEWER).json()
    assert [(b["bay"], summary(b)) for b in planogram["bays"]] == [(1, [[("A", 1)]]), (2, [[("B", 1)]])]
