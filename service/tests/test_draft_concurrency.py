"""Extraction runs as a background job while Managers edit the same Draft Planogram; no write
may silently lose another. Background jobs run inline here, so each test interleaves a request
with an Extraction through the Recognizer, or by pausing one between reading and saving the Draft."""

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import MANAGER, VIEWER, FakeRecognizer, register_fixture, shelf_row, upload_photo
from planogram import extraction
from planogram.models import BayLayout, Planogram, Product
from planogram.planograms import with_bay
from planogram.recognition import Recognition
from test_extraction import extract, stock_catalogue, summary
from test_review import block_ids, blocks_url, draft_from


@pytest.fixture
def fixture(client: TestClient) -> dict[str, Any]:
    stock_catalogue(client, "A", "B", "C")
    return register_fixture(client)


@pytest.fixture
def draft(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any]) -> dict[str, Any]:
    """A Draft with "A" on Bay 1 and "B" on Bay 2."""
    draft_from(client, recognizer, fixture, shelf_row(1, "A"), bay=1)
    return draft_from(client, recognizer, fixture, shelf_row(1, "B"), bay=2)


def bays(client: TestClient, planogram_id: str) -> dict[int, Any]:
    planogram = client.get(f"/planograms/{planogram_id}", headers=VIEWER).json()
    return {b["bay"]: summary(b) for b in planogram["bays"]}


class WatchedLock:
    """The repository's lock, noting when a thread has to wait for it."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.contended = threading.Event()

    def __enter__(self) -> None:
        if not self._lock.acquire(blocking=False):
            self.contended.set()
            self._lock.acquire()

    def __exit__(self, *_: object) -> None:
        self._lock.release()


@pytest.fixture
def lock(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> WatchedLock:
    watched = WatchedLock()
    monkeypatch.setattr(client.app.state.context.repo, "_lock", watched)  # type: ignore[attr-defined]
    return watched


def run_until_done_or_waiting(thread: threading.Thread, lock: WatchedLock) -> None:
    """Starts ``thread`` and returns once it has finished or is waiting for the repository."""
    thread.start()
    while thread.is_alive() and not lock.contended.wait(timeout=0.01):
        pass


def reextract_bay_1(client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], *skus: str) -> dict[str, Any]:
    recognizer.result = Recognition(facings=shelf_row(1, *skus), empty_regions=[])
    return extract(client, upload_photo(client, fixture, bay=1).json()["id"])


def test_an_edit_made_during_an_extraction_survives_it(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], draft: dict[str, Any]
) -> None:
    [b] = block_ids(draft, bay=2)
    edits: list[int] = []
    recognizer.while_recognizing = lambda: edits.append(
        client.patch(f"{blocks_url(draft, 2)}/blocks/{b}", json={"sku": "C", "facings": 2}, headers=MANAGER).status_code
    )

    job = reextract_bay_1(client, recognizer, fixture, "B", "B")

    assert edits == [200]
    assert job["status"] == "done"
    assert bays(client, draft["id"]) == {1: [[("B", 2)]], 2: [[("C", 2)]]}


def test_an_extraction_waits_for_an_edit_already_under_way(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], draft: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch, lock: WatchedLock,
) -> None:
    [b] = block_ids(draft, bay=2)
    photo = upload_photo(client, fixture, bay=1).json()
    recognizer.result = Recognition(facings=shelf_row(1, "B", "B"), empty_regions=[])
    repo = client.app.state.context.repo  # type: ignore[attr-defined]
    get_product = repo.get_product
    extracting = threading.Thread(target=lambda: extract(client, photo["id"]))

    def extract_between_reading_and_saving_the_draft(sku: str) -> Product | None:
        if extracting.ident is None:
            run_until_done_or_waiting(extracting, lock)
        return get_product(sku)

    monkeypatch.setattr(repo, "get_product", extract_between_reading_and_saving_the_draft)
    response = client.patch(f"{blocks_url(draft, 2)}/blocks/{b}", json={"sku": "C"}, headers=MANAGER)
    extracting.join()

    assert response.status_code == 200
    assert bays(client, draft["id"]) == {1: [[("B", 2)]], 2: [[("C", 1)]]}


def test_an_edit_waits_for_an_extraction_already_saving(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], draft: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch, lock: WatchedLock,
) -> None:
    [b] = block_ids(draft, bay=2)
    responses: list[int] = []
    edit = threading.Thread(
        target=lambda: responses.append(
            client.patch(f"{blocks_url(draft, 2)}/blocks/{b}", json={"sku": "C"}, headers=MANAGER).status_code
        )
    )

    def edit_between_reading_and_saving_the_draft(planogram: Planogram, layout: BayLayout) -> Planogram:
        run_until_done_or_waiting(edit, lock)
        return with_bay(planogram, layout)

    monkeypatch.setattr(extraction, "with_bay", edit_between_reading_and_saving_the_draft)
    reextract_bay_1(client, recognizer, fixture, "B", "B")
    edit.join()

    assert responses == [200]
    assert bays(client, draft["id"]) == {1: [[("B", 2)]], 2: [[("C", 1)]]}


def test_an_edit_to_a_block_replaced_by_extraction_is_refused(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], draft: dict[str, Any]
) -> None:
    [a] = block_ids(draft, bay=1)
    reextract_bay_1(client, recognizer, fixture, "B", "B")
    url = f"{blocks_url(draft, 1)}/blocks/{a}"

    assert client.patch(url, json={"sku": "C"}, headers=MANAGER).status_code == 409
    assert client.delete(url, headers=MANAGER).status_code == 409
    assert client.post(f"{url}/resolve", json={"existing_sku": "C"}, headers=MANAGER).status_code == 409
    assert bays(client, draft["id"]) == {1: [[("B", 2)]], 2: [[("B", 1)]]}


def test_an_edit_from_an_outdated_view_of_another_bay_applies_to_the_latest_draft(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], draft: dict[str, Any]
) -> None:
    [b] = block_ids(draft, bay=2)
    reextract_bay_1(client, recognizer, fixture, "C")

    response = client.patch(f"{blocks_url(draft, 2)}/blocks/{b}", json={"facings": 3}, headers=MANAGER)

    assert response.status_code == 200
    assert bays(client, draft["id"]) == {1: [[("C", 1)]], 2: [[("B", 3)]]}


def test_an_extraction_finishing_after_approval_starts_a_new_draft(
    client: TestClient, recognizer: FakeRecognizer, fixture: dict[str, Any], draft: dict[str, Any]
) -> None:
    approvals: list[int] = []
    recognizer.while_recognizing = lambda: approvals.append(
        client.post(f"/planograms/{draft['id']}/approve", headers=MANAGER).status_code
    )

    job = reextract_bay_1(client, recognizer, fixture, "C")

    assert approvals == [200]
    approved = client.get(f"/planograms/{draft['id']}", headers=VIEWER).json()
    assert approved["status"] == "Approved"
    assert bays(client, draft["id"]) == {1: [[("A", 1)]], 2: [[("B", 1)]]}
    new_draft = client.get(job["result_url"], headers=VIEWER).json()
    assert new_draft["status"] == "Draft"
    assert bays(client, new_draft["id"]) == {1: [[("C", 1)]], 2: [[("B", 1)]]}
