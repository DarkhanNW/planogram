"""Compliance Comparer: pure domain logic comparing the observed layout of a Bay with its
Approved Planogram, producing Deviations and the Compliance Score. Each cause is reported as
exactly one Deviation.

On each Shelf, planned Blocks are paired in order with observed Blocks of the same Product
(the longest such pairing). A paired Block is in its correct Position; its Facings up to the
planned count are present. An observed Block of a planned Product left unpaired is Misplaced,
standing in for the nearest planned Block of that Product still short of Facings (or, when
none is short, the nearest one).

The pairs split each Shelf into stretches. Empty space in a stretch is a Gap of the planned
Facings missing there, claimed from the left, and empty space no stretch's Blocks could claim
goes to any other planned Block on the Shelf still short of Facings. Each run of empty space
a Block claims is one Gap. A planned Block with Facings absent beyond the empty space it
claimed is Missing when nothing of it is in place, its space taken by something else, and
otherwise has a Wrong Facing Count; so does a paired Block with more Facings than planned,
unless they fill the space of a neighbour short of Facings, with nothing else stocked between
them. A neighbour spreading into a short
Block's space is one cause, reported once as that Block's Missing or Wrong Facing Count; only
the spreading Block's Facings beyond what its neighbours lack are its own Wrong Facing Count.
Anything observed that the Bay's plan does not hold, including Unknown Products, is Unexpected.

Precision first: every observed run whose confidence is below the threshold is an Unverified
area. It never pairs, so it cannot confirm a Product in place or push others out of theirs. A
Deviation resting on one is not reported, and the planned Facings it accounts for are
Unverified: they count towards neither the Compliance Score nor Coverage's verified share.

A planned Shelf with nothing observed on it at all, not even empty space, is one recognition
did not see, as when the Shelf Photo is cropped. All its planned Facings are Unverified too,
and a Misplaced Block of the same Product elsewhere never stands in for them: they may well be
in place. It stands in for a planned Block on an observed Shelf instead, and names one on a
Shelf with nothing observed only when the Product is planned nowhere else. The Shelf is not listed as an Unverified area: with nothing observed there, there is
no box to give it."""

from dataclasses import dataclass, field
from itertools import groupby

from planogram.geometry import Box
from planogram.layout import ObservedShelf, Segment
from planogram.models import Block, BayLayout, Deviation, DeviationKind, Position, UnverifiedArea


@dataclass
class Comparison:
    deviations: list[Deviation]
    compliance_score: float | None
    """None when no planned Facing could be verified."""
    coverage: float
    unverified: list[UnverifiedArea]


@dataclass
class _Finding:
    deviation: Deviation
    planned_facings: int = 0
    """The planned Facings it accounts for, left Unverified when it is not confident."""


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
    segment: int | None = None
    """The observed Block it is paired with."""
    present: int = 0
    elsewhere: int = 0
    """Facings standing Misplaced elsewhere in the Bay."""
    extra: int = 0
    """Facings observed beyond the planned count, not yet accounted for."""
    stretch: tuple[int, int] = (-1, -1)
    """For a Block left unpaired, the segments (exclusive) of the pairs either side of it."""
    neighbours: tuple[int, int] = (-1, -1)
    """For a Block left unpaired, the planned Blocks of the pairs either side of it."""
    empty: list[_EmptyFacing] = field(default_factory=list)

    @property
    def missing(self) -> int:
        return self.block.facings - self.present - self.elsewhere - len(self.empty)


@dataclass
class _Shelf:
    number: int
    plan: list[_PlannedBlock]
    segments: list[Segment]
    stocked: list[int]
    """The segments that are not empty space."""
    observed_at: dict[int, Position]
    """Each stocked segment's observed Position."""
    pairs: list[tuple[int, int]]
    """(planned index, segment index) of each planned Block in its correct Position."""

    @property
    def unseen(self) -> bool:
        """Nothing at all, not even empty space, was observed on it."""
        return not self.segments

    @property
    def unpaired(self) -> list[int]:
        paired = {s for _, s in self.pairs}
        return [i for i in self.stocked if i not in paired]


def compare(planned: BayLayout, observed: list[ObservedShelf], threshold: float) -> Comparison:
    """``threshold`` is the confidence below which recognition leaves an area Unverified."""
    planned_shelves = {s.number: s.blocks for s in planned.shelves}
    observed_shelves = {s.number: s.segments for s in observed}
    shelves = [
        _paired_shelf(planned.bay, n, planned_shelves.get(n, []), observed_shelves.get(n, []), threshold)
        for n in sorted(planned_shelves.keys() | observed_shelves.keys())
    ]
    findings = _misplaced(shelves, planned.skus)
    for shelf in shelves:
        findings += _shelf_deviations(shelf, planned.skus)
    confident = [f for f in findings if f.deviation.confidence >= threshold]
    unverified = sum(f.planned_facings for f in findings if f.deviation.confidence < threshold)
    unverified += sum(p.block.facings for s in shelves if s.unseen for p in s.plan)

    present = sum(p.present for s in shelves for p in s.plan)
    total = sum(p.block.facings for s in shelves for p in s.plan)
    verifiable = total - unverified
    return Comparison(
        deviations=sorted((f.deviation for f in confident), key=lambda d: (_shelf_of(d), d.box.x)),
        compliance_score=present / verifiable if verifiable else None,
        coverage=verifiable / total if total else 1.0,
        unverified=[
            UnverifiedArea(shelf=s.number, box=segment.box, confidence=segment.confidence)
            for s in shelves
            for segment in s.segments
            if segment.confidence < threshold
        ],
    )


def _paired_shelf(bay: int, number: int, blocks: list[Block], segments: list[Segment], threshold: float) -> _Shelf:
    def at(order: int, facings: int) -> Position:
        return Position(bay=bay, shelf=number, order=order + 1, facings=facings)

    plan = [_PlannedBlock(block=b, position=at(i, b.facings)) for i, b in enumerate(blocks)]
    stocked = [i for i, s in enumerate(segments) if not s.empty]
    observed_at = {i: at(order, segments[i].facings) for order, i in enumerate(stocked)}
    pairs = _pair([b.sku for b in blocks], [(i, segments[i].sku) for i in stocked if segments[i].confidence >= threshold])
    for p, s in pairs:
        plan[p].observed, plan[p].segment = observed_at[s], s
        plan[p].present = min(blocks[p].facings, segments[s].facings)
        plan[p].extra = max(0, segments[s].facings - blocks[p].facings)
    return _Shelf(number=number, plan=plan, segments=segments, stocked=stocked, observed_at=observed_at, pairs=pairs)


def _misplaced(shelves: list[_Shelf], planned_skus: set[str]) -> list[_Finding]:
    """Each observed Block of a planned Product off its planned Position is Misplaced, standing
    in for the nearest planned Block of that Product short of Facings, or else the nearest. A
    planned Block on an unseen Shelf is named only when the Product is planned on no other
    Shelf, and is never stood in for."""
    unseen = {s.number for s in shelves if s.unseen}
    findings = []
    for shelf in shelves:
        for i in shelf.unpaired:
            segment, observed = shelf.segments[i], shelf.observed_at[i]
            if segment.sku not in planned_skus:
                continue
            planned = min(
                (p for s in shelves for p in s.plan if p.block.sku == segment.sku),
                key=lambda p: (
                    p.position.shelf in unseen,
                    p.missing <= 0,
                    abs(p.position.shelf - shelf.number),
                    abs(p.position.order - observed.order),
                ),
            )
            standing_in = 0 if planned.position.shelf in unseen else max(0, min(planned.missing, segment.facings))
            planned.elsewhere += standing_in
            findings.append(_Finding(Deviation(
                kind=DeviationKind.MISPLACED, sku=segment.sku, facings=segment.facings, planned=planned.position,
                observed=observed, box=segment.box, confidence=segment.confidence,
            ), standing_in))
    return findings


def _shelf_deviations(shelf: _Shelf, planned_skus: set[str]) -> list[_Finding]:
    """The Shelf's Gaps, Missing, Wrong Facing Counts and Unexpected."""
    plan, segments = shelf.plan, shelf.segments

    # Each stretch between neighbouring pairs (and the Shelf's ends) offers its empty space to
    # the planned Blocks bounding it and those planned inside it, from the left.
    bounds = [(-1, -1)] + shelf.pairs + [(len(plan), len(segments))]
    unclaimed: list[_EmptyFacing] = []
    for (left_p, left_s), (right_p, right_s) in zip(bounds, bounds[1:]):
        for p in plan[left_p + 1 : right_p]:
            p.stretch, p.neighbours = (left_s, right_s), (left_p, right_p)
        empty = [f for i in range(left_s + 1, right_s) if segments[i].empty for f in _empty_facings(i, segments[i])]
        unclaimed += _claim(plan[max(left_p, 0) : right_p + 1], empty)
    _claim(plan, unclaimed)

    # A short Block's space taken by the extra Facings of a neighbour is one cause: the
    # neighbour spreading. It is reported once, as the short Block's Missing or Wrong Facing
    # Count. Missing Blocks take their neighbours' extra Facings first; a Block in place only
    # from a neighbour in place next to it, with nothing else stocked between them.
    missing_blocks = [
        (p, taken) for p in plan if p.observed is None and p.missing > 0 for taken in [_taken_by(p, segments)] if taken
    ]
    spread_into = [(p, p.neighbours) for p, _ in missing_blocks] + [
        (p, _neighbours_in_place(k, plan, segments)) for k, p in enumerate(plan) if p.segment is not None and p.missing > 0
    ]
    for p, neighbours in spread_into:
        need = p.missing
        for n in neighbours:
            if 0 <= n < len(plan):
                take = min(need, plan[n].extra)
                plan[n].extra -= take
                need -= take

    return [
        _Finding(Deviation(
            kind=DeviationKind.GAP, sku=p.block.sku, facings=len(run), planned=p.position, observed=p.observed,
            box=Box.union([f.box for f in run]), confidence=min(f.confidence for f in run),
        ), len(run))
        for p in plan
        for run in (list(r) for _, r in groupby(sorted(p.empty, key=lambda f: f.box.x), key=lambda f: f.run))
    ] + [
        _Finding(Deviation(
            kind=DeviationKind.MISSING, sku=p.block.sku, facings=p.missing, planned=p.position, observed=None,
            box=Box.union([s.box for s in taken]), confidence=min(s.confidence for s in taken),
        ), p.missing)
        for p, taken in missing_blocks
    ] + [
        _Finding(Deviation(
            kind=DeviationKind.WRONG_FACING_COUNT, sku=p.block.sku, facings=p.extra or p.missing, planned=p.position,
            observed=p.observed, box=segments[p.segment].box, confidence=segments[p.segment].confidence,
        ), max(0, p.missing))
        for p in plan
        if p.segment is not None and (p.extra or p.missing > 0)
    ] + [
        _Finding(Deviation(
            kind=DeviationKind.UNEXPECTED, sku=segments[i].sku, facings=segments[i].facings, planned=None,
            observed=shelf.observed_at[i], box=segments[i].box, confidence=segments[i].confidence,
        ))
        for i in shelf.unpaired
        if segments[i].unknown or segments[i].sku not in planned_skus
    ]


def _taken_by(p: _PlannedBlock, segments: list[Segment]) -> list[Segment]:
    """What has taken the space of an unpaired planned Block: what stands between the pairs
    either side of it or, when nothing does, those neighbours. Nothing when nothing was observed
    there at all, which shows nothing about the Block."""
    left, right = p.stretch
    taken = [s for s in segments[left + 1 : right] if not s.empty]
    return taken or [segments[i] for i in (left, right) if 0 <= i < len(segments)]


def _neighbours_in_place(k: int, plan: list[_PlannedBlock], segments: list[Segment]) -> tuple[int, ...]:
    """The planned Blocks either side of the paired Block ``k`` that are in place next to it, with
    nothing but empty space observed between them."""
    def side_by_side(a: int, b: int) -> bool:
        return all(segments[i].empty for i in range(a + 1, b))

    here = plan[k].segment
    assert here is not None
    return tuple(
        n for n in (k - 1, k + 1)
        if 0 <= n < len(plan) and (there := plan[n].segment) is not None and side_by_side(min(here, there), max(here, there))
    )


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
    as (planned index, segment index) pairs; among equally long ones, the one keeping Blocks
    closest to their planned order. Unknown Products never pair."""
    n, m = len(planned), len(observed)
    # best[i][j]: (pairs, -total order shift) of the best pairing of planned[i:] with observed[j:].
    best = [[(0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            options = [best[i + 1][j], best[i][j + 1]]
            if planned[i] is not None and planned[i] == observed[j][1]:
                pairs, shift = best[i + 1][j + 1]
                options.append((pairs + 1, shift - abs(i - j)))
            best[i][j] = max(options)
    pairs_found, i, j = [], 0, 0
    while i < n and j < m:
        if best[i][j] == best[i + 1][j]:
            i += 1
        elif best[i][j] == best[i][j + 1]:
            j += 1
        else:
            pairs_found.append((i, observed[j][0]))
            i, j = i + 1, j + 1
    return pairs_found


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
