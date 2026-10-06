"""The real Recognizer (ADR 0001), running entirely inside the service:

1. Detect: an off-the-shelf open-vocabulary detector (OWLv2) boxes every Facing; Shelves are
   found by clustering Facings on their bottom edges (the Shelf lines).
2. Match: each Facing crop is described by an image embedding (DINOv2) plus a colour
   histogram and compared with the reference images of the candidate Products. A Facing whose
   best match is below the threshold, or does not clearly beat the runner-up, is an Unknown
   Product. Colour matters: embeddings alone confuse packs of the same shape and layout.

Empty Shelf regions are the gaps between Facings on a Shelf that are wide enough to hold a
Facing. No custom training; models download once from the Hugging Face hub (weights only;
no image ever leaves the service)."""

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
            if not detections:
                return Recognition(facings=[], empty_regions=[])
            shelves = assign_shelves([d.box for d in detections])
            descriptors = self._describe([crop(image, d.box) for d in detections])
            primary, secondary = self._index(candidates), self._index(fallback)
            facings = []
            for detection, shelf, descriptor in zip(detections, shelves, descriptors):
                sku, confidence = self._match(descriptor, primary)
                if sku is None and secondary:
                    sku, confidence = self._match(descriptor, secondary)
                facings.append(RecognizedFacing(box=detection.box, shelf=shelf, sku=sku, confidence=confidence))
            return Recognition(facings=facings, empty_regions=find_empty_regions(image, facings))

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


def assign_shelves(boxes: list[Box]) -> list[int]:
    """Shelf number (1 = bottom) for each box, clustering boxes whose bottom edges sit on the
    same Shelf line. A new Shelf starts wherever consecutive bottom edges (from the bottom of
    the photo up) are further apart than a third of a typical Facing's height."""
    tolerance = median(b.h for b in boxes) / 3
    order = sorted(range(len(boxes)), key=lambda i: boxes[i].bottom, reverse=True)
    shelves = [0] * len(boxes)
    shelf, previous = 1, boxes[order[0]].bottom
    for i in order:
        if previous - boxes[i].bottom > tolerance:
            shelf += 1
        shelves[i], previous = shelf, boxes[i].bottom
    return shelves


def find_empty_regions(image: np.ndarray, facings: list[RecognizedFacing]) -> list[EmptyRegion]:
    """Gaps between Facings on a Shelf, and between the Bay's edges and its outermost Facings,
    that could hold a Facing. Confidence falls as the gap shows more edges, since a busy gap
    probably holds a product the detector missed."""
    width = median(f.box.w for f in facings)
    left_edge, right_edge = min(f.box.x for f in facings), max(f.box.right for f in facings)
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 80, 160)
    regions = []
    for shelf in sorted({f.shelf for f in facings}):
        on_shelf = sorted((f.box for f in facings if f.shelf == shelf), key=lambda b: b.x)
        top, bottom = min(b.y for b in on_shelf), max(b.bottom for b in on_shelf)
        start = left_edge
        for box in on_shelf + [Box(x=right_edge, y=top, w=0, h=0)]:
            if box.x - start >= EMPTY_GAP * width:
                gap = Box(x=start, y=top, w=box.x - start, h=bottom - top)
                density = float(np.count_nonzero(crop(edges, gap))) / max(1, gap.w * gap.h)
                confidence = float(np.clip(1.0 - density / 0.12, 0.0, 0.95))
                regions.append(EmptyRegion(box=gap, shelf=shelf, confidence=confidence))
            start = max(start, box.right)
    return regions
