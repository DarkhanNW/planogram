"""Planogram lifecycle: Draft (editable) → Approved (never changes) → Superseded."""

from planogram.context import Context
from planogram.errors import NotFound
from planogram.models import BayLayout, Planogram, PlanogramStatus
from planogram.repository import new_id


def get_planogram(ctx: Context, planogram_id: str) -> Planogram:
    planogram = ctx.repo.get_planogram(planogram_id)
    if planogram is None:
        raise NotFound("Planogram not found")
    return planogram


def current_approved(ctx: Context, fixture_id: str) -> Planogram | None:
    approved = ctx.repo.list_planograms(fixture_id, PlanogramStatus.APPROVED)
    return approved[0] if approved else None


def open_draft(ctx: Context, fixture_id: str) -> Planogram:
    """The Fixture's Draft Planogram, starting one from the current Approved Planogram (so
    re-extracting one Bay keeps the approved layout of the others) if there is none."""
    drafts = ctx.repo.list_planograms(fixture_id, PlanogramStatus.DRAFT)
    if drafts:
        return drafts[0]
    approved = current_approved(ctx, fixture_id)
    return Planogram(
        id=new_id(),
        fixture_id=fixture_id,
        status=PlanogramStatus.DRAFT,
        created_at=ctx.clock(),
        bays=[bay.model_copy(deep=True) for bay in approved.bays] if approved else [],
    )


def with_bay(planogram: Planogram, layout: BayLayout) -> Planogram:
    bays = [b for b in planogram.bays if b.bay != layout.bay] + [layout]
    return planogram.model_copy(update={"bays": sorted(bays, key=lambda b: b.bay)})
