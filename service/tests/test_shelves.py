"""Shelves found by the real Recognizer from synthetic Facing boxes, when Facings are stacked."""

import cv2
import numpy as np

from planogram.geometry import Box
from planogram.layout import build_layout
from planogram.recognition import Recognition, RecognizedFacing
from planogram.vision import find_bay

WIDTH, HEIGHT = 640, 480
BAY_LEFT, BAY_RIGHT = 40, 600


def photo(*shelf_lines: int) -> np.ndarray:
    """A plain Bay with a dark Shelf edge at the top of each Shelf line."""
    image = np.full((HEIGHT, WIDTH, 3), 215, np.uint8)
    for y in shelf_lines:
        cv2.rectangle(image, (BAY_LEFT, y), (BAY_RIGHT, y + 8), (40, 40, 40), -1)
    return image


def pack(x: int, bottom: int, h: int = 100) -> Box:
    return Box(x=x, y=bottom - h, w=60, h=h)


def shelves(image: np.ndarray, boxes: list[Box]) -> list[int]:
    bay = find_bay(image, boxes)
    return [bay.shelf_of(i) for i in range(len(boxes))]


def test_a_two_high_stack_stands_on_the_shelf_of_the_facing_beneath_it() -> None:
    singles = [pack(40, 460), pack(100, 460)]
    stack = [pack(160, 460), pack(160, 360)]
    above = [pack(40, 240), pack(100, 240)]
    boxes = singles + stack + above
    image = photo()

    bay = find_bay(image, boxes)
    skus = ["RICE", "RICE", "BEANS", "BEANS", "PASTA", "PASTA"]
    recognition = Recognition(
        facings=[
            RecognizedFacing(box=b, shelf=bay.shelf_of(i), sku=sku, confidence=0.9)
            for i, (b, sku) in enumerate(zip(boxes, skus))
        ],
        empty_regions=[],
    )
    layout = build_layout(recognition)

    assert len(bay.shelves) == 2
    assert [(s.number, [(b.sku, b.facings) for b in s.segments]) for s in layout] == [
        (1, [("RICE", 2), ("BEANS", 2)]),
        (2, [("PASTA", 2)]),
    ]


def test_a_stacked_facing_with_nothing_detected_beneath_it_stands_on_the_shelf_it_reaches_into() -> None:
    # The upper Facing of a stack of short packs whose lower Facing the detector missed: its
    # bottom edge is lower than the tops of the Facings beside it, so no Shelf can be there.
    boxes = [pack(40, 460), pack(100, 460), pack(220, 400, h=60), pack(40, 240), pack(100, 240)]

    assert shelves(photo(), boxes) == [1, 1, 1, 2, 2]


def test_a_stacked_facing_between_two_shelf_lines_stands_on_the_lower_shelf() -> None:
    # Level with the tops of the Facings beside it and with nothing detected beneath it, but
    # the Shelf lines around it leave no room for a Shelf of its own.
    boxes = [pack(40, 470), pack(100, 470), pack(220, 370), pack(40, 260), pack(100, 260)]

    assert shelves(photo(470, 260, 30), boxes) == [1, 1, 1, 2, 2]


def test_shelf_lines_missed_by_line_detection_do_not_stack_a_shelf_onto_the_one_below() -> None:
    # Only the bottom Shelf line and the top of the Bay are found: the Shelf lines between
    # them are missing, which says nothing about stacking.
    boxes = [pack(40, 470), pack(100, 470), pack(40, 340), pack(100, 340), pack(40, 210)]

    assert shelves(photo(470, 30), boxes) == [1, 1, 2, 2, 3]


def test_a_facing_just_above_a_facing_on_the_shelf_below_stands_on_its_own_shelf() -> None:
    boxes = [pack(40, 460), pack(100, 460), pack(40, 340), pack(100, 340), pack(40, 220)]

    assert shelves(photo(), boxes) == [1, 1, 2, 2, 3]
