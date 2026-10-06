"""The real Recognizer (ADR 0001), running entirely inside the service:

1. Detect: an off-the-shelf open-vocabulary detector (OWLv2) boxes every Facing; Shelves are
   found by clustering Facings on their bottom edges, plus any Shelf line (a long horizontal
   edge) that no Facings stand on: an empty Shelf.
2. Match: each Facing crop is described by an image embedding (DINOv2) plus a colour
   histogram and compared with the reference images of the candidate Products. A Facing whose
   best match is below the threshold, or does not clearly beat the runner-up, is an Unknown
   Product. Colour matters: embeddings alone confuse packs of the same shape and layout.

Empty Shelf regions are empty Shelves, and the gaps between Facings on a Shelf, or between
the Bay's edges and its outermost Facings, that are wide enough to hold a Facing. No custom
training; models download once from the Hugging Face hub (weights only; no image ever leaves
the service)."""

import threading
from dataclasses import dataclass
from statistics import median
from typing import Any

import cv2
import numpy as np

from planogram.geometry import Box
from planogram.images import ImageStore
from planogram.models import Product
from planogram.photos import decode_image
from planogram.recognition import EmptyRegion, Recognition, RecognizedFacing
from planogram.settings import Settings

DETECTION_QUERIES = [
    "a product on a store shelf",
    "a bottle",
    "a can",
    "a carton",
    "a box",
    "a packet",
]
NMS_OVERLAP = 0.3
MAX_FACING_AREA = 0.2
"""Detections covering more of the photo than this are whole Shelves or Fixtures, not Facings."""
MIN_RELATIVE_HEIGHT = 0.55
"""Detections shorter than this share of a typical Facing are caps, labels or price tags."""
INSIDE_ANOTHER = 0.6
"""Detections with this share of their area inside a larger detection are parts of it."""
EMPTY_GAP = 0.6
"""A gap at least this many typical Facing widths wide is empty Shelf space."""
LINE_COVERAGE = 0.5
"""A horizontal edge across at least this share of the photo's width is a Shelf line."""
LINE_CONTRAST = 60
"""Vertical brightness gradient (Sobel) a pixel needs to count towards a Shelf line."""
NO_FACINGS_HEIGHT = 0.1
"""With no Facings to measure, a typical Facing is taken as this share of the photo's height."""
COLOUR_WEIGHT = 0.25
"""Share of the match similarity that comes from colour; the rest is the embedding."""


@dataclass
class Detection:
    box: Box
    score: float


@dataclass
class Descriptor:
    embedding: np.ndarray
    colour: np.ndarray


class TwoStageRecognizer:
    def __init__(self, settings: Settings, images: ImageStore) -> None:
        self._settings = settings
        self._images = images
        self._lock = threading.Lock()
        self._models: dict[str, Any] | None = None
        self._references: dict[str, Descriptor] = {}

    def recognize(self, image: np.ndarray, candidates: list[Product], fallback: list[Product]) -> Recognition:
        with self._lock:
            detections = self._detect(image)
            bay = find_bay(image, [d.box for d in detections])
            if not detections:
                return Recognition(facings=[], empty_regions=find_empty_regions(image, bay, []))
            descriptors = self._describe([crop(image, d.box) for d in detections])
            primary, secondary = self._index(candidates), self._index(fallback)
            facings = []
            for i, (detection, descriptor) in enumerate(zip(detections, descriptors)):
                sku, confidence = self._match(descriptor, primary)
                if sku is None and secondary:
                    sku, confidence = self._match(descriptor, secondary)
                facings.append(RecognizedFacing(box=detection.box, shelf=bay.shelf_of(i), sku=sku, confidence=confidence))
            return Recognition(facings=facings, empty_regions=find_empty_regions(image, bay, facings))

    # Stage 1: detection

    def _detect(self, image: np.ndarray) -> list[Detection]:
        import torch

        models = self._load()
        height, width = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        inputs = models["detector_processor"](text=[DETECTION_QUERIES], images=rgb, return_tensors="pt")
        with torch.no_grad():
            outputs = models["detector"](**inputs)
        scores = torch.sigmoid(outputs.logits[0]).max(dim=-1).values.numpy()
        # OWLv2 pads the photo to a square; boxes are (cx, cy, w, h) relative to that square.
        side = max(width, height)
        raw = outputs.pred_boxes[0].numpy() * side
        keep = scores >= self._settings.detection_threshold
        boxes = [[float(cx - w / 2), float(cy - h / 2), float(w), float(h)] for cx, cy, w, h in raw[keep]]
        kept_scores = [float(s) for s in scores[keep]]
        detections = []
        for i in cv2.dnn.NMSBoxes(boxes, kept_scores, self._settings.detection_threshold, NMS_OVERLAP):
            x, y, w, h = boxes[int(i)]
            box = Box(x=round(x), y=round(y), w=round(w), h=round(h)).clipped(width, height)
            if box is not None and box.w * box.h <= MAX_FACING_AREA * width * height:
                detections.append(Detection(box=box, score=kept_scores[int(i)]))
        return drop_fragments(drop_groups(detections))

    # Stage 2: matching

    def _describe(self, crops: list[np.ndarray]) -> list[Descriptor]:
        import torch

        models = self._load()
        embeddings = []
        for start in range(0, len(crops), 32):
            batch = [cv2.cvtColor(c, cv2.COLOR_BGR2RGB) for c in crops[start : start + 32]]
            inputs = models["embedding_processor"](images=batch, return_tensors="pt")
            with torch.no_grad():
                output = models["embedder"](**inputs)
            embeddings.append(output.pooler_output.numpy())
        matrix = np.concatenate(embeddings)
        matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
        return [Descriptor(embedding=e, colour=colour_histogram(c)) for e, c in zip(matrix, crops)]

    def _index(self, products: list[Product]) -> list[tuple[str, Descriptor]]:
        """One entry per reference image, labelled with its Product's SKU."""
        missing = [i for p in products for i in p.reference_images if i.image_key not in self._references]
        if missing:
            images = [decode_image(self._images.get(i.image_key)) for i in missing]
            for reference, descriptor in zip(missing, self._describe(images)):
                self._references[reference.image_key] = descriptor
        return [(p.sku, self._references[i.image_key]) for p in products for i in p.reference_images]

    def _match(self, facing: Descriptor, index: list[tuple[str, Descriptor]]) -> tuple[str | None, float]:
        """The matched SKU and the confidence in that identity; for an Unknown Product, the
        confidence that it is none of the candidates."""
        if not index:
            return None, 0.0
        best: dict[str, float] = {}
        for sku, reference in index:
            best[sku] = max(best.get(sku, -1.0), similarity(facing, reference))
        ranked = sorted(best.values(), reverse=True)
        top_sku = max(best, key=lambda sku: best[sku])
        runner_up = ranked[1] if len(ranked) > 1 else 0.0
        if ranked[0] >= self._settings.match_threshold and ranked[0] - runner_up >= self._settings.match_margin:
            return top_sku, ranked[0]
        return None, float(np.clip(1.0 - ranked[0], 0.0, 1.0))

    def _load(self) -> dict[str, Any]:
        if self._models is None:
            from transformers import AutoImageProcessor, AutoModel, Owlv2ForObjectDetection, Owlv2Processor

            s = self._settings
            self._models = {
                "detector_processor": Owlv2Processor.from_pretrained(s.detector_model),
                "detector": Owlv2ForObjectDetection.from_pretrained(s.detector_model).eval(),
                "embedding_processor": AutoImageProcessor.from_pretrained(s.embedding_model),
                "embedder": AutoModel.from_pretrained(s.embedding_model).eval(),
            }
        return self._models


def similarity(a: Descriptor, b: Descriptor) -> float:
    embedding = float(a.embedding @ b.embedding)
    colour = float(np.minimum(a.colour, b.colour).sum())
    return (1 - COLOUR_WEIGHT) * embedding + COLOUR_WEIGHT * colour


def colour_histogram(image: np.ndarray) -> np.ndarray:
    """Hue/saturation histogram of the middle of a crop (edges often show the neighbours)."""
    height, width = image.shape[:2]
    middle = image[height // 6 : height - height // 6, width // 6 : width - width // 6]
    hsv = cv2.cvtColor(middle if middle.size else image, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256]).flatten()
    total = float(histogram.sum())
    return histogram / total if total else histogram


def crop(image: np.ndarray, box: Box) -> np.ndarray:
    return image[box.y : box.bottom, box.x : box.right]


def _overlap(inner: Box, outer: Box) -> float:
    """Share of ``inner``'s area that lies inside ``outer``."""
    w = min(inner.right, outer.right) - max(inner.x, outer.x)
    h = min(inner.bottom, outer.bottom) - max(inner.y, outer.y)
    return max(0, w) * max(0, h) / max(1, inner.w * inner.h)


def drop_groups(detections: list[Detection]) -> list[Detection]:
    """Drops boxes that contain two or more other boxes: a run of Facings, not one Facing."""
    return [
        d for d in detections
        if sum(1 for other in detections if other is not d and _overlap(other.box, d.box) > 0.9) < 2
    ]


def drop_fragments(detections: list[Detection]) -> list[Detection]:
    """Drops caps, labels and price tags: boxes mostly inside a larger box, or much shorter
    than a typical Facing."""
    if not detections:
        return detections
    whole = [
        d for d in detections
        if not any(
            other.box.w * other.box.h > d.box.w * d.box.h and _overlap(d.box, other.box) >= INSIDE_ANOTHER
            for other in detections
        )
    ]
    typical = median(d.box.h for d in whole)
    return [d for d in whole if d.box.h >= MIN_RELATIVE_HEIGHT * typical]


@dataclass
class ShelfLine:
    """A long horizontal edge across the Bay: the front of a Shelf, or the top of the Bay."""

    y: int
    left: int
    right: int


@dataclass
class ShelfSpace:
    """The space for Facings on one Shelf. On a stocked Shelf it spans its Facings; on an empty
    Shelf, from its Shelf line up to the Shelf above it."""

    number: int
    top: int
    bottom: int
    facings: list[int]
    """Indices of the Facing boxes standing on this Shelf."""


@dataclass
class Bay:
    """The Bay a Shelf Photo shows: its horizontal extent and its Shelves."""

    left: int
    right: int
    shelves: list[ShelfSpace]
    """Every Shelf, stocked or empty, from the bottom (number 1) up."""

    def shelf_of(self, facing: int) -> int:
        """The Shelf number of the Facing box at this index."""
        return next(s.number for s in self.shelves if facing in s.facings)


def find_shelf_lines(image: np.ndarray) -> list[ShelfLine]:
    """Horizontal edges crossing at least ``LINE_COVERAGE`` of the photo, from the top down."""
    height = image.shape[0]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    strong = (np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)) > LINE_CONTRAST).astype(np.uint8)
    # Thicken vertically so a slightly tilted Shelf edge still lines up along a row.
    slack = max(3, height // 100)
    horizontal = cv2.dilate(strong, np.ones((slack, 1), np.uint8)) > 0
    rows = np.flatnonzero(horizontal.mean(axis=1) >= LINE_COVERAGE)
    if not rows.size:
        return []
    lines = []
    for band in np.split(rows, np.flatnonzero(np.diff(rows) > slack) + 1):
        columns = np.flatnonzero(horizontal[band[0] : band[-1] + 1].any(axis=0))
        lines.append(ShelfLine(y=int(band.mean()), left=int(columns[0]), right=int(columns[-1]) + 1))
    return lines


def find_bay(image: np.ndarray, boxes: list[Box]) -> Bay:
    """The Bay's Shelves, stocked and empty, and its horizontal extent, from its Shelf lines
    and the Facing boxes."""
    height, width = image.shape[:2]
    lines = find_shelf_lines(image)
    typical_height = median(b.h for b in boxes) if boxes else NO_FACINGS_HEIGHT * height
    stocked = _stocked_shelves(boxes, typical_height / 3)
    empty = _empty_shelves(lines, stocked, typical_height)
    shelves = sorted(stocked + empty, key=lambda s: s.bottom, reverse=True)
    for number, shelf in enumerate(shelves, start=1):
        shelf.number = number

    left, right = (int(median(l.left for l in lines)), int(median(l.right for l in lines))) if lines else (0, width)
    if boxes:
        left, right = min(left, *(b.x for b in boxes)), max(right, *(b.right for b in boxes))
    return Bay(left=left, right=right, shelves=shelves)


def _stocked_shelves(boxes: list[Box], tolerance: float) -> list[ShelfSpace]:
    """Facings whose bottom edges sit together stand on one Shelf: a new Shelf starts wherever
    consecutive bottom edges (from the bottom of the photo up) are further apart than
    ``tolerance``. Unnumbered."""
    groups: list[list[int]] = []
    previous = 0
    for i in sorted(range(len(boxes)), key=lambda i: boxes[i].bottom, reverse=True):
        if not groups or previous - boxes[i].bottom > tolerance:
            groups.append([])
        groups[-1].append(i)
        previous = boxes[i].bottom
    return [
        ShelfSpace(number=0, top=min(boxes[i].y for i in g), bottom=max(boxes[i].bottom for i in g), facings=g)
        for g in groups
    ]


def _empty_shelves(lines: list[ShelfLine], stocked: list[ShelfSpace], typical_height: float) -> list[ShelfSpace]:
    """A Shelf line that no Facings stand on or cross is an empty Shelf when the space above it,
    up to the next Shelf, could hold a typical Facing; the topmost line, with nothing above
    it, is the top of the Bay. Lines closer than a third of a Facing are one Shelf edge.
    Unnumbered."""
    tolerance = typical_height / 3
    free: list[int] = []
    for line in sorted(lines, key=lambda line: line.y):
        stood_on_or_crossed = any(
            abs(line.y - s.bottom) <= tolerance or s.top + tolerance < line.y < s.bottom for s in stocked
        )
        if not stood_on_or_crossed and not (free and line.y - free[-1] <= tolerance):
            free.append(line.y)
    empty = []
    for y in free:
        above = [other for other in free if other < y] + [s.bottom for s in stocked if s.bottom < y]
        if above and y - max(above) >= typical_height:
            empty.append(ShelfSpace(number=0, top=max(above), bottom=y, facings=[]))
    return empty


def find_empty_regions(image: np.ndarray, bay: Bay, facings: list[RecognizedFacing]) -> list[EmptyRegion]:
    """Empty Shelves, and gaps between Facings on a Shelf or between the Bay's edges and its
    outermost Facings, that could hold a Facing. Confidence falls as the space shows more
    edges, since a busy space probably holds a product the detector missed."""
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 80, 160)

    def region(left: int, right: int, shelf: ShelfSpace) -> EmptyRegion:
        box = Box(x=left, y=shelf.top, w=right - left, h=shelf.bottom - shelf.top)
        density = float(np.count_nonzero(crop(edges, box))) / max(1, box.w * box.h)
        return EmptyRegion(box=box, shelf=shelf.number, confidence=float(np.clip(1.0 - density / 0.12, 0.0, 0.95)))

    width = median(f.box.w for f in facings) if facings else 0
    regions = []
    for shelf in bay.shelves:
        on_shelf = sorted((f.box for f in facings if f.shelf == shelf.number), key=lambda b: b.x)
        start = bay.left
        for box in on_shelf + [Box(x=bay.right, y=shelf.top, w=0, h=0)]:
            if box.x - start >= EMPTY_GAP * width:
                regions.append(region(start, box.x, shelf))
            start = max(start, box.right)
    return regions
