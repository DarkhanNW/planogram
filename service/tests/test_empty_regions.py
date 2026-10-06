"""Empty Shelf space found by the real Recognizer, on synthetic Shelf Photos of one Bay."""

import cv2
import numpy as np

from planogram.geometry import Box
from planogram.recognition import EmptyRegion, RecognizedFacing
from planogram.vision import find_bay, find_empty_regions

WIDTH, HEIGHT = 640, 480
BAY_LEFT, BAY_RIGHT = 40, 600
SHELF_LINES = [470, 340, 210, 80]
"""The tops of the Shelf edges, from the bottom; the last is the top of the Bay."""
FACING_W, FACING_H = 60, 100
COLOURS = [(40, 60, 200), (200, 80, 40), (60, 180, 60), (30, 160, 220)]


def bay_photo() -> np.ndarray:
    """A plain Bay with dark Shelf edges and nothing on the Shelves."""
    image = np.full((HEIGHT, WIDTH, 3), 215, np.uint8)
    for y in SHELF_LINES:
        cv2.rectangle(image, (BAY_LEFT, y), (BAY_RIGHT, y + 8), (40, 40, 40), -1)
    return image


def stock(image: np.ndarray, shelf_line: int, *xs: int) -> list[Box]:
    """Puts a plain pack standing on the Shelf line at each x; returns their boxes."""
    boxes = []
    for i, x in enumerate(xs):
        box = Box(x=x, y=shelf_line - FACING_H, w=FACING_W, h=FACING_H)
        cv2.rectangle(image, (box.x, box.y), (box.right - 1, box.bottom - 1), COLOURS[i % len(COLOURS)], -1)
        boxes.append(box)
    return boxes


def recognize(image: np.ndarray, boxes: list[Box]) -> tuple[list[RecognizedFacing], list[EmptyRegion]]:
    bay = find_bay(image, boxes)
    facings = [
        RecognizedFacing(box=b, shelf=shelf, sku="SKU", confidence=0.9) for b, shelf in zip(boxes, map(bay.shelf_of, range(len(boxes))))
    ]
    return facings, find_empty_regions(image, bay, facings)


def spans(regions: list[EmptyRegion]) -> list[tuple[int, int]]:
    """Each region's left and right, snapped to the Bay's edges when within a few pixels of them."""

    def snap(x: int) -> int:
        return next((edge for edge in (BAY_LEFT, BAY_RIGHT) if abs(x - edge) <= 3), x)

    return [(snap(r.box.x), snap(r.box.right)) for r in regions]


def full_row(image: np.ndarray, shelf_line: int) -> list[Box]:
    return stock(image, shelf_line, *range(BAY_LEFT, BAY_RIGHT - FACING_W + 1, FACING_W))


def test_a_shelf_with_no_facings_is_reported_in_sequence_with_the_other_shelves() -> None:
    image = bay_photo()
    bottom = full_row(image, SHELF_LINES[0])
    top = full_row(image, SHELF_LINES[2])

    facings, empty = recognize(image, bottom + top)

    assert {f.shelf for f in facings[: len(bottom)]} == {1}
    assert {f.shelf for f in facings[len(bottom) :]} == {3}
    assert [r.shelf for r in empty] == [2]
    region = empty[0].box
    assert spans(empty) == [(BAY_LEFT, BAY_RIGHT)]
    assert region.bottom >= SHELF_LINES[1] - 4 and region.y <= SHELF_LINES[2] + 12
    assert empty[0].confidence > 0.7


def test_gaps_between_the_bays_edges_and_the_outermost_facings_are_reported() -> None:
    image = bay_photo()
    middle = stock(image, SHELF_LINES[0], 200, 260, 320)
    full = full_row(image, SHELF_LINES[1])

    _, empty = recognize(image, middle + full)

    on_bottom = [r for r in empty if r.shelf == 1]
    assert spans(on_bottom) == [(BAY_LEFT, 200), (380, BAY_RIGHT)]
    assert all(r.confidence > 0.7 for r in on_bottom)


def test_an_edge_gap_too_narrow_for_a_facing_is_not_reported() -> None:
    image = bay_photo()
    boxes = stock(image, SHELF_LINES[0], BAY_LEFT + 20, BAY_LEFT + 80) + full_row(image, SHELF_LINES[1])

    _, empty = recognize(image, boxes)

    assert spans([r for r in empty if r.shelf == 1]) == [(BAY_LEFT + 140, BAY_RIGHT)]


def test_gaps_between_facings_are_still_reported() -> None:
    image = bay_photo()
    boxes = stock(image, SHELF_LINES[0], BAY_LEFT, BAY_LEFT + 60, 280, 340, 400, 460, 520)
    boxes += full_row(image, SHELF_LINES[1]) + full_row(image, SHELF_LINES[2])

    _, empty = recognize(image, boxes)

    assert [(r.shelf, r.box.x, r.box.right) for r in empty] == [(1, BAY_LEFT + 120, 280)]
    assert empty[0].box.y == SHELF_LINES[0] - FACING_H and empty[0].box.bottom == SHELF_LINES[0]
    assert empty[0].confidence > 0.7


def test_a_busy_gap_probably_holds_a_missed_product_so_gets_low_confidence() -> None:
    image = bay_photo()
    boxes = stock(image, SHELF_LINES[0], BAY_LEFT, BAY_LEFT + 60, 280, 340, 400, 460, 520)
    boxes += full_row(image, SHELF_LINES[1]) + full_row(image, SHELF_LINES[2])
    # A busy pack the detector missed, between the second and third Facings.
    for x in range(BAY_LEFT + 124, 276, 6):
        cv2.line(image, (x, SHELF_LINES[0] - FACING_H + 4), (x, SHELF_LINES[0] - 4), (20, 20, 20), 2)

    _, empty = recognize(image, boxes)

    assert [(r.box.x, r.box.right) for r in empty] == [(BAY_LEFT + 120, 280)]
    assert empty[0].confidence < 0.3


def test_every_shelf_of_a_bay_with_no_facings_is_reported() -> None:
    _, empty = recognize(bay_photo(), [])

    assert [r.shelf for r in empty] == [1, 2, 3]
    assert spans(empty) == [(BAY_LEFT, BAY_RIGHT)] * 3
    assert all(r.confidence > 0.7 for r in empty)
