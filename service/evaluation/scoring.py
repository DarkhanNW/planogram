"""Scores one photo's Extraction and Compliance Check against its labels. Counts, not rates,
so photos can be pooled; rates are taken over the pooled counts.

Extraction is scored per Block. On each Shelf the extracted Blocks are paired in order with
the labelled Blocks of the same Product (or both Unknown Product), the longest such pairing.
A paired labelled Block is identified; its facing count is exact when the counts agree. An
unpaired extracted Block that names a Product is confidently wrong, unless it is a fragment
of a paired Block split off by Unknown Facings: the same Product, next to that Block but for
Unknown Products (and other fragments) between them, with the paired Block short of its
labelled Facings. A fragment costs the facing count, not identity. An Unknown Product is
never confidently wrong; it costs identification only.

Deviations are matched one to one on kind, Product and Shelf (the planned Shelf; for
Unexpected, the Shelf it was found on). Every expected and every reported Deviation counts,
and each reported Deviation pairs with at most one expected Deviation. So a report beyond
the expected number of a (kind, Product, Shelf) costs precision, and one short of it costs
recall: one cause reported as several Deviations shows up as a precision loss."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, fields

from planogram.models import Deviation, Shelf

from evaluation.labels import ExpectedDeviation, LabelledShelf


@dataclass
class Counts:
    labelled_blocks: int = 0
    identified_blocks: int = 0
    exact_facing_counts: int = 0
    named_blocks: int = 0
    """Extracted Blocks naming a Product (not Unknown Product)."""
    confidently_wrong: int = 0
    expected_deviations: int = 0
    reported_deviations: int = 0
    matched_deviations: int = 0

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})


def score_extraction(labelled: list[LabelledShelf], extracted: list[Shelf]) -> Counts:
    counts = Counts()
    truth = {s.number: [(b.sku, b.facings) for b in s.blocks] for s in labelled}
    found = {s.number: [(b.sku, b.facings) for b in s.blocks] for s in extracted}
    for number in truth.keys() | found.keys():
        want, got = truth.get(number, []), found.get(number, [])
        pairs = pair([sku for sku, _ in want], [sku for sku, _ in got])
        counts.labelled_blocks += len(want)
        counts.identified_blocks += len(pairs)
        counts.exact_facing_counts += sum(1 for i, j in pairs if want[i][1] == got[j][1])
        counts.named_blocks += sum(1 for sku, _ in got if sku is not None)
        labelled_for = {j: i for i, j in pairs}
        short = {j for j, i in labelled_for.items() if got[j][1] < want[i][1]}
        counts.confidently_wrong += sum(
            1
            for j, (sku, _) in enumerate(got)
            if sku is not None and j not in labelled_for and not _fragment(j, [s for s, _ in got], short)
        )
    return counts


def _fragment(j: int, skus: list[str | None], short: set[int]) -> bool:
    """Whether extracted Block ``j`` is split off a paired Block short of Facings, ``short``:
    the same Product, with only Unknown Products or more of that Product between them."""
    for step in (-1, 1):
        k = j + step
        while 0 <= k < len(skus) and (skus[k] is None or (skus[k] == skus[j] and k not in short)):
            k += step
        if 0 <= k < len(skus) and k in short and skus[k] == skus[j]:
            return True
    return False


def score_deviations(expected: list[ExpectedDeviation], reported: list[Deviation]) -> Counts:
    want = Counter((d.kind, d.sku, d.shelf) for d in expected)
    got = Counter((d.kind, d.sku, shelf_of(d)) for d in reported)
    return Counts(
        expected_deviations=want.total(),
        reported_deviations=got.total(),
        matched_deviations=(want & got).total(),
    )


def shelf_of(deviation: Deviation) -> int:
    """The planned Shelf; for Unexpected, the Shelf it was found on. Every Deviation has one."""
    position = deviation.planned or deviation.observed
    assert position is not None
    return position.shelf


def pair(labelled: Sequence[str | None], extracted: Sequence[str | None]) -> list[tuple[int, int]]:
    """The longest in-order pairing of equal Products, as (labelled index, extracted index)."""
    n, m = len(labelled), len(extracted)
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            matched = best[i + 1][j + 1] + 1 if labelled[i] == extracted[j] else 0
            best[i][j] = max(best[i + 1][j], best[i][j + 1], matched)
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if labelled[i] == extracted[j] and best[i][j] == best[i + 1][j + 1] + 1:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif best[i][j] == best[i + 1][j]:
            i += 1
        else:
            j += 1
    return pairs


@dataclass(frozen=True)
class Metric:
    name: str
    target: float
    higher_is_better: bool = True

    def met(self, value: float) -> bool:
        return value >= self.target if self.higher_is_better else value <= self.target


BLOCK_IDENTIFICATION = Metric("Block identification", 0.90)
CONFIDENTLY_WRONG = Metric("Confidently wrong", 0.02, higher_is_better=False)
EXACT_FACING_COUNT = Metric("Exact facing count", 0.85)
DEVIATION_PRECISION = Metric("Deviation precision", 0.90)
DEVIATION_RECALL = Metric("Deviation recall", 0.80)


def rates(counts: Counts) -> dict[Metric, tuple[float | None, int]]:
    """Each MVP metric's value (None when there is nothing to measure it on) and the number it
    was measured on."""

    def rate(part: int, whole: int) -> tuple[float | None, int]:
        return (part / whole if whole else None), whole

    return {
        BLOCK_IDENTIFICATION: rate(counts.identified_blocks, counts.labelled_blocks),
        CONFIDENTLY_WRONG: rate(counts.confidently_wrong, counts.named_blocks),
        EXACT_FACING_COUNT: rate(counts.exact_facing_counts, counts.identified_blocks),
        DEVIATION_PRECISION: rate(counts.matched_deviations, counts.reported_deviations),
        DEVIATION_RECALL: rate(counts.matched_deviations, counts.expected_deviations),
    }
