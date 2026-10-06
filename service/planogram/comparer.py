"""Compliance Comparer: pure domain logic comparing the observed layout of a Bay with its
Approved Planogram, producing Deviations and the Compliance Score.

On each Shelf, planned Blocks are paired in order with observed Blocks of the same Product
(the longest such pairing). A paired Block is in its correct Position; its Facings up to the
planned count are present. The pairs split the Shelf into stretches; empty space in a stretch
is a Gap of the planned Facings missing there, claimed from the left, and empty space no
stretch's Blocks could claim goes to any other planned Block still short of Facings. Each run
of empty space a Block claims is one Gap. Anything observed that the Bay's plan does not hold,
including Unknown Products, is Unexpected; a planned Product off its planned Position is left
for Misplaced."""

from dataclasses import dataclass, field
from itertools import groupby

from planogram.geometry import Box
from planogram.layout import ObservedShelf, Segment
from planogram.models import Block, BayLayout, Deviation, DeviationKind, Position


@dataclass
class Comparison:
    deviations: list[Deviation]
    compliance_score: float


@dataclass
class _EmptyFacing:
    run: int
    """The empty segment it is part of."""
    box: Box
    confidence: float


@dataclass
class _PlannedBlock:
    block: Block
    position: Position
    observed: Position | None = None
    present: int = 0
    empty: list[_EmptyFacing] = field(default_factory=list)

    @property
    def missing(self) -> int:
        return self.block.facings - self.present - len(self.empty)


def compare(planned: BayLayout, observed: list[ObservedShelf]) -> Comparison:
    planned_shelves = {s.number: s.blocks for s in planned.shelves}
    observed_shelves = {s.number: s.segments for s in observed}
    deviations: list[Deviation] = []
    present = total = 0
    for shelf in sorted(planned_shelves.keys() | observed_shelves.keys()):
        blocks = planned_shelves.get(shelf, [])
        found, in_place = _compare_shelf(planned.bay, shelf, blocks, observed_shelves.get(shelf, []), planned.skus)
        deviations += found
        present += in_place
        total += sum(b.facings for b in blocks)
    deviations.sort(key=lambda d: (_shelf_of(d), d.box.x))
    return Comparison(deviations=deviations, compliance_score=present / total if total else 1.0)


def _compare_shelf(
    bay: int, shelf: int, blocks: list[Block], segments: list[Segment], planned_skus: set[str]
) -> tuple[list[Deviation], int]:
    """The Shelf's Deviations and how many of its planned Facings are present in place."""

    def at(order: int, facings: int) -> Position:
        return Position(bay=bay, shelf=shelf, order=order + 1, facings=facings)

    plan = [_PlannedBlock(block=b, position=at(i, b.facings)) for i, b in enumerate(blocks)]
    stocked = [i for i, s in enumerate(segments) if not s.empty]
    observed_at = {i: at(order, segments[i].facings) for order, i in enumerate(stocked)}
    pairs = _pair([b.sku for b in blocks], [(i, segments[i].sku) for i in stocked])
    for p, s in pairs:
        plan[p].observed = observed_at[s]
        plan[p].present = min(blocks[p].facings, segments[s].facings)

    # Each stretch between neighbouring pairs (and the Shelf's ends) offers its empty space to
    # the planned Blocks bounding it and those planned inside it, from the left.
    bounds = [(-1, -1)] + pairs + [(len(plan), len(segments))]
    unclaimed: list[_EmptyFacing] = []
    for (left_p, left_s), (right_p, right_s) in zip(bounds, bounds[1:]):
        empty = [f for i in range(left_s + 1, right_s) if segments[i].empty for f in _empty_facings(i, segments[i])]
        unclaimed += _claim(plan[max(left_p, 0) : right_p + 1], empty)
    _claim(plan, unclaimed)

    paired = {s for _, s in pairs}
    deviations = [
        Deviation(
            kind=DeviationKind.GAP, sku=p.block.sku, facings=len(run), planned=p.position, observed=p.observed,
            box=Box.union([f.box for f in run]), confidence=min(f.confidence for f in run),
        )
        for p in plan
        for run in (list(r) for _, r in groupby(sorted(p.empty, key=lambda f: f.box.x), key=lambda f: f.run))
    ] + [
        Deviation(
            kind=DeviationKind.UNEXPECTED, sku=segments[i].sku, facings=segments[i].facings, planned=None,
            observed=observed_at[i], box=segments[i].box, confidence=segments[i].confidence,
        )
        for i in stocked
        if i not in paired and (segments[i].unknown or segments[i].sku not in planned_skus)
    ]
    return deviations, sum(p.present for p in plan)


def _claim(claimants: list[_PlannedBlock], empty: list[_EmptyFacing]) -> list[_EmptyFacing]:
    """Gives the empty Facings, from the left, to the claimants short of Facings, in order;
    returns those left over."""
    for claimant in claimants:
        take = max(0, min(claimant.missing, len(empty)))
        claimant.empty += empty[:take]
        empty = empty[take:]
    return empty


def _pair(planned: list[str | None], observed: list[tuple[int, str | None]]) -> list[tuple[int, int]]:
    """The longest in-order pairing of planned Blocks with observed Blocks of the same Product,
    as (planned index, segment index) pairs. Unknown Products never pair."""
    n, m = len(planned), len(observed)
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            same = planned[i] is not None and planned[i] == observed[j][1]
            best[i][j] = best[i + 1][j + 1] + 1 if same else max(best[i + 1][j], best[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if planned[i] is not None and planned[i] == observed[j][1]:
            pairs.append((i, observed[j][0]))
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def _empty_facings(run: int, segment: Segment) -> list[_EmptyFacing]:
    """Empty Shelf space split into the Facings it would hold, left to right."""
    box, n = segment.box, segment.facings
    edges = [box.x + round(box.w * k / n) for k in range(n + 1)]
    return [
        _EmptyFacing(run=run, box=Box(x=left, y=box.y, w=right - left, h=box.h), confidence=segment.confidence)
        for left, right in zip(edges, edges[1:])
    ]


def _shelf_of(deviation: Deviation) -> int:
    position = deviation.planned or deviation.observed
    return position.shelf if position else 0
