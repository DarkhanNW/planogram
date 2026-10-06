"""Person Blurrer (ADR 0003): people in a Shelf Photo are found and blurred before anything
is stored. Finding people sits behind ``PersonBlurrer`` so tests can script it."""

from typing import Protocol

import cv2
import numpy as np

from planogram.geometry import Box


class PersonBlurrer(Protocol):
    def find_people(self, image: np.ndarray) -> list[Box]:
        """Boxes around every face and body in a BGR image."""
        ...


def blur_people(image: np.ndarray, people: list[Box]) -> np.ndarray:
    """Returns a copy with every person box made unrecognisable: pixelated, then blurred."""
    result = image.copy()
    height, width = image.shape[:2]
    for person in people:
        box = person.clipped(width, height)
        if box is None:
            continue
        region = result[box.y : box.bottom, box.x : box.right]
        small = cv2.resize(region, (max(1, box.w // 16), max(1, box.h // 16)), interpolation=cv2.INTER_AREA)
        pixelated = cv2.resize(small, (box.w, box.h), interpolation=cv2.INTER_LINEAR)
        kernel = max(3, (min(box.w, box.h) // 4) | 1)
        result[box.y : box.bottom, box.x : box.right] = cv2.GaussianBlur(pixelated, (kernel, kernel), 0)
    return result


class OpenCvPersonBlurrer:
    """Off-the-shelf detectors bundled with OpenCV, running inside the service: a HOG
    pedestrian detector for bodies and Haar cascades for frontal and profile faces. Found
    regions are padded, since missing part of a person is worse than blurring some shelf."""

    PADDING = 0.15

    def __init__(self) -> None:
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())  # type: ignore[attr-defined]
        cascades = cv2.data.haarcascades  # type: ignore[attr-defined]
        self._faces = [
            cv2.CascadeClassifier(cascades + "haarcascade_frontalface_default.xml"),
            cv2.CascadeClassifier(cascades + "haarcascade_profileface.xml"),
        ]

    def find_people(self, image: np.ndarray) -> list[Box]:
        height, width = image.shape[:2]
        scale = min(1.0, 1280 / max(width, height))
        small = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
        gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))

        found: list[tuple[int, int, int, int]] = []
        bodies, weights = self._hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        found += [(b[0], b[1], b[2], b[3]) for b, w in zip(bodies, weights) if float(w) > 0.3]
        for cascade in self._faces:
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
            found += [(f[0], f[1], f[2], f[3]) for f in faces]

        boxes = []
        for x, y, w, h in found:
            pad_x, pad_y = w * self.PADDING, h * self.PADDING
            box = Box(
                x=int((x - pad_x) / scale), y=int((y - pad_y) / scale),
                w=int((w + 2 * pad_x) / scale), h=int((h + 2 * pad_y) / scale),
            ).clipped(width, height)
            if box is not None:
                boxes.append(box)
        return boxes
