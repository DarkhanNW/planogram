"""Layout Builder: turns a Recognition of one Bay into Shelves (from the bottom) of runs
(from the left). Adjacent Facings of the same Product on a Shelf form one run; so do adjacent
empty regions. Each Unknown Product Facing is a run of its own: nothing says two adjacent
Facings that match no Product are the same Product."""

from collections.abc import Iterable
from itertools import groupby
from statistics import median

from pydantic import BaseModel

from planogram.geometry import Box
from planogram.models import Block, Shelf
from planogram.recognition import Recognition
from planogram.repository import new_id


class Segment(BaseModel):
    """A run on an observed Shelf: Facings of one Product, one Unknown Product, or empty space."""

    sku: str | None
    empty: bool
    facings: int
    box: Box
    confidence: float

    @property
    def unknown(self) -> bool:
        return not self.empty and self.sku is None


class ObservedShelf(BaseModel):
    number: int
    segments: list[Segment]


def build_layout(recognition: Recognition) -> list[ObservedShelf]:
    facing_width = _typical_facing_width(recognition)
    items: list[tuple[int, Segment]] = [
        (f.shelf, Segment(sku=f.sku, empty=False, facings=1, box=f.box, confidence=f.confidence))
        for f in recognition.facings
    ] + [
        (r.shelf, Segment(sku=None, empty=True, facings=max(1, round(r.box.w / facing_width)), box=r.box, confidence=r.confidence))
        for r in recognition.empty_regions
    ]
    shelves = []
    for number, on_shelf in groupby(sorted(items, key=lambda i: (i[0], i[1].box.x)), key=lambda i: i[0]):
        shelves.append(ObservedShelf(number=number, segments=[_merge(run) for run in _runs(s for _, s in on_shelf)]))
    return shelves


def to_shelves(observed: list[ObservedShelf]) -> list[Shelf]:
    """The Planogram Shelves for Extraction: what is on each Shelf, ignoring empty space."""
    return [
        Shelf(
            number=shelf.number,
            blocks=[Block(id=new_id(), sku=s.sku, facings=s.facings, box=s.box) for s in shelf.segments if not s.empty],
        )
        for shelf in observed
    ]


def _runs(segments: Iterable[Segment]) -> list[list[Segment]]:
    runs: list[list[Segment]] = []
    for segment in segments:
        last = runs[-1][-1] if runs else None
        if last is not None and not segment.unknown and (last.empty, last.sku) == (segment.empty, segment.sku):
            runs[-1].append(segment)
        else:
            runs.append([segment])
    return runs


def _merge(run: list[Segment]) -> Segment:
    first = run[0]
    return Segment(
        sku=first.sku,
        empty=first.empty,
        facings=sum(s.facings for s in run),
        box=Box.union([s.box for s in run]),
        confidence=min(s.confidence for s in run),
    )


def _typical_facing_width(recognition: Recognition) -> float:
    if recognition.facings:
        return float(median(f.box.w for f in recognition.facings))
    # No Facings to measure: assume packs about half as wide as the Shelf is tall.
    return max(1.0, median(r.box.h for r in recognition.empty_regions) / 2) if recognition.empty_regions else 1.0
