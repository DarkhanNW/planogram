"""Score history: how a Bay's or Fixture's Compliance Score and Coverage change over time,
marking when a newly Approved Planogram changed what the Bays are measured against."""

from datetime import datetime
from typing import TypeAlias

from planogram.context import Context
from planogram.errors import NotFound
from planogram.models import BayLayout, PlanogramChange, PlanogramStatus, ScoreHistory, ScorePoint
from planogram.repository import as_utc


def score_history(
    ctx: Context, fixture_id: str, bay: int | None = None, since: datetime | None = None, until: datetime | None = None
) -> ScoreHistory:
    """The Fixture's history, or only one Bay's when ``bay`` is given; ``since`` and ``until``
    are inclusive."""
    fixture = ctx.repo.get_fixture(fixture_id)
    if fixture is None:
        raise NotFound("Fixture not found")
    if bay is not None and bay not in fixture.bays:
        raise NotFound(f"The Fixture has no Bay {bay}")
    since, until = (as_utc(t) if t is not None else None for t in (since, until))
    checks = ctx.repo.list_compliance_checks(fixture_id=fixture_id, bay=bay, since=since, until=until)
    points = [
        ScorePoint(
            check_id=c.id, bay=c.bay, submitted_at=c.submitted_at, compliance_score=c.compliance_score,
            coverage=c.coverage, planogram_id=c.planogram_id,
        )
        for c in reversed(checks)
    ]
    changes = [
        change.model_copy(update={"bays": [bay]}) if bay is not None else change
        for change in _planogram_changes(ctx, fixture_id)
        if (bay is None or bay in change.bays)
        and (since is None or change.approved_at >= since)
        and (until is None or change.approved_at <= until)
    ]
    return ScoreHistory(points=points, planogram_changes=changes)


def _planogram_changes(ctx: Context, fixture_id: str) -> list[PlanogramChange]:
    """Every approval of the Fixture that changed some Bay's planned layout, oldest first. An
    approval that left a Bay's layout as it was (re-extracting it unchanged) is no change to it."""
    approvals = sorted(
        [
            (p.approved_at, p) for p in reversed(ctx.repo.list_planograms(fixture_id))
            if p.status in (PlanogramStatus.APPROVED, PlanogramStatus.SUPERSEDED) and p.approved_at is not None
        ],
        key=lambda a: a[0],
    )
    changes = []
    previous: dict[int, BayPlan] = {}
    for approved_at, planogram in approvals:
        current = {layout.bay: _plan(layout) for layout in planogram.bays}
        changed = sorted(b for b, plan in current.items() if previous.get(b) != plan)
        if changed:
            changes.append(PlanogramChange(planogram_id=planogram.id, approved_at=approved_at, bays=changed))
        previous = current
    return changes


BayPlan: TypeAlias = list[tuple[int, list[tuple[str | None, int]]]]
"""Per Shelf, its number and its Blocks' Products and facing counts in order."""


def _plan(layout: BayLayout) -> BayPlan:
    """What a Bay is measured against: its Products and facing counts in order, Shelf by Shelf."""
    return [(s.number, [(b.sku, b.facings) for b in s.blocks]) for s in layout.shelves]
