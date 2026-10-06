from typing import Annotated

from fastapi import APIRouter, Depends

from planogram.access import AnyRole
from planogram.context import Context, get_context
from planogram.models import Planogram
from planogram.planograms import get_planogram

router = APIRouter(tags=["Planograms"])
Ctx = Annotated[Context, Depends(get_context)]


@router.get("/planograms/{planogram_id}")
def get(planogram_id: str, _: AnyRole, ctx: Ctx) -> Planogram:
    return get_planogram(ctx, planogram_id)


@router.get("/fixtures/{fixture_id}/planograms")
def list_for_fixture(fixture_id: str, _: AnyRole, ctx: Ctx) -> list[Planogram]:
    """Every Planogram of the Fixture, newest first: Drafts, the Approved one and Superseded ones."""
    return ctx.repo.list_planograms(fixture_id)
