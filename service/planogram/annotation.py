"""Annotated Photo: a Compliance Check's Deviations drawn over its (blurred) Shelf Photo, each
outlined at its box and labelled with its kind, with Unverified areas shaded lightly beneath."""

import cv2
import numpy as np

from planogram.geometry import Box
from planogram.models import Deviation, DeviationKind, UnverifiedArea

# BGR, matching the development UI.
KIND_COLOURS = {
    DeviationKind.GAP: (9, 83, 180),
    DeviationKind.MISSING: (93, 24, 190),
    DeviationKind.WRONG_FACING_COUNT: (237, 58, 124),
    DeviationKind.MISPLACED: (144, 116, 14),
    DeviationKind.UNEXPECTED: (40, 40, 198),
}
UNVERIFIED_COLOUR = (125, 114, 105)
UNVERIFIED_OPACITY = 0.3
FONT = cv2.FONT_HERSHEY_SIMPLEX
LABEL_REACH = 3
"""How many label heights a label may move away from its box to avoid another label."""


def annotate(image: np.ndarray, deviations: list[Deviation], unverified: list[UnverifiedArea]) -> np.ndarray:
    """Returns a copy of a BGR image with the Deviations and Unverified areas drawn on it."""
    height, width = image.shape[:2]
    size = max(width, height)
    thickness = max(2, round(size / 300))
    scale = max(0.4, size / 1500)
    result = image.copy()

    shaded = result.copy()
    for area in unverified:
        box = area.box.clipped(width, height)
        if box is not None:
            cv2.rectangle(shaded, (box.x, box.y), (box.right - 1, box.bottom - 1), UNVERIFIED_COLOUR, cv2.FILLED)
    result = cv2.addWeighted(shaded, UNVERIFIED_OPACITY, result, 1 - UNVERIFIED_OPACITY, 0)

    drawn = [(d, box) for d in deviations if (box := d.box.clipped(width, height)) is not None]
    inset = thickness // 2  # keeps each line inside its box, off its neighbours
    for deviation, box in drawn:
        corners = (box.x + inset, box.y + inset), (box.right - 1 - inset, box.bottom - 1 - inset)
        cv2.rectangle(result, *corners, KIND_COLOURS[deviation.kind], thickness)
    # Labels last, so no outline crosses one.
    labels: list[Box] = []
    for deviation, box in drawn:
        _label(result, deviation.kind.value, box, KIND_COLOURS[deviation.kind], scale, labels)
    return result


def _label(image: np.ndarray, text: str, box: Box, colour: tuple[int, int, int], scale: float, placed: list[Box]) -> None:
    """Draws the label just above the box, or inside its top edge when there is no room above,
    moving it a little up or down past labels already placed so dense Shelves stay readable;
    overlapping one is better than drifting away from its box."""
    height, width = image.shape[:2]
    weight = max(1, round(scale * 2))
    (text_w, text_h), baseline = cv2.getTextSize(text, FONT, scale, weight)
    pad = max(2, round(scale * 4))
    label_w, label_h = text_w + 2 * pad, text_h + baseline + 2 * pad
    x = max(0, min(box.x, width - label_w))

    # Nearest the box first: just above it, just inside it, then further out either way.
    tops = [y for i in range(LABEL_REACH) for y in (box.y - (i + 1) * label_h, box.y + i * label_h)]
    spots = [Box(x=x, y=y, w=label_w, h=label_h) for y in tops if 0 <= y <= height - label_h]
    spots = spots or [Box(x=x, y=0, w=label_w, h=label_h)]
    spot = next((s for s in spots if not any(_overlaps(s, p) for p in placed)), spots[0])
    placed.append(spot)

    cv2.rectangle(image, (spot.x, spot.y), (spot.right - 1, spot.bottom - 1), colour, cv2.FILLED)
    origin = (spot.x + pad, spot.bottom - pad - baseline)
    cv2.putText(image, text, origin, FONT, scale, (255, 255, 255), weight, cv2.LINE_AA)


def _overlaps(a: Box, b: Box) -> bool:
    return a.x < b.right and b.x < a.right and a.y < b.bottom and b.y < a.bottom
