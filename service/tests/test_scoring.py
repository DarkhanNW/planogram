from evaluation.labels import ExpectedDeviation
from evaluation.scoring import DEVIATION_PRECISION, DEVIATION_RECALL, rates, score_deviations
from planogram.geometry import Box
from planogram.models import Deviation, DeviationKind, Position


def expected_gap(sku: str = "COKE-330", shelf: int = 1) -> ExpectedDeviation:
    return ExpectedDeviation(kind=DeviationKind.GAP, sku=sku, shelf=shelf)


def reported_gap(sku: str = "COKE-330", shelf: int = 1) -> Deviation:
    return Deviation(
        kind=DeviationKind.GAP,
        sku=sku,
        facings=1,
        planned=Position(bay=1, shelf=shelf, order=1, facings=2),
        observed=None,
        box=Box(x=0, y=0, w=10, h=10),
        confidence=1.0,
    )


def test_two_gaps_of_one_product_on_one_shelf_match_two() -> None:
    counts = score_deviations([expected_gap(), expected_gap()], [reported_gap(), reported_gap()])

    assert (counts.expected_deviations, counts.reported_deviations, counts.matched_deviations) == (2, 2, 2)


def test_an_extra_report_costs_precision() -> None:
    counts = score_deviations([expected_gap()], [reported_gap(), reported_gap()])

    assert rates(counts)[DEVIATION_PRECISION] == (1 / 2, 2)
    assert rates(counts)[DEVIATION_RECALL] == (1.0, 1)


def test_an_unreported_gap_costs_recall() -> None:
    counts = score_deviations([expected_gap(), expected_gap()], [reported_gap()])

    assert rates(counts)[DEVIATION_RECALL] == (1 / 2, 2)
    assert rates(counts)[DEVIATION_PRECISION] == (1.0, 1)


def test_deviations_match_only_on_the_same_kind_product_and_shelf() -> None:
    unexpected = ExpectedDeviation(kind=DeviationKind.UNEXPECTED, sku="COKE-330", shelf=1)
    counts = score_deviations(
        [expected_gap(), expected_gap(shelf=2), unexpected], [reported_gap(), reported_gap("FANTA-330")]
    )

    assert (counts.expected_deviations, counts.reported_deviations, counts.matched_deviations) == (3, 2, 1)
