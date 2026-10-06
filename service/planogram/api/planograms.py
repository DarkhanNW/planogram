from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from planogram import planograms
from planogram.access import AnyRole, ManagerRole
from planogram.context import Context, get_context
from planogram.models import BlockChange, BlockIn, Planogram, Resolution

router = APIRouter(tags=["Planograms"])
Ctx = Annotated[Context, Depends(get_context)]


@router.get("/planograms/{planogram_id}")
def get(planogram_id: str, _: AnyRole, ctx: Ctx) -> Planogram:
    return planograms.get_planogram(ctx, planogram_id)


@router.get("/fixtures/{fixture_id}/planograms")
def list_for_fixture(fixture_id: str, _: AnyRole, ctx: Ctx) -> list[Planogram]:
    """Every Planogram of the Fixture, newest first: Drafts, the Approved one and Superseded ones."""
    return ctx.repo.list_planograms(fixture_id)


@router.patch("/planograms/{planogram_id}/bays/{bay}/blocks/{block_id}")
def change_block(planogram_id: str, bay: int, block_id: str, body: BlockChange, _: ManagerRole, ctx: Ctx) -> Planogram:
    """Changes a Draft Block's Product and/or facing count."""
    return planograms.change_block(ctx, planogram_id, bay, block_id, body.sku, body.facings)


@router.delete("/planograms/{planogram_id}/bays/{bay}/blocks/{block_id}")
def delete_block(planogram_id: str, bay: int, block_id: str, _: ManagerRole, ctx: Ctx) -> Planogram:
    return planograms.delete_block(ctx, planogram_id, bay, block_id)


@router.post("/planograms/{planogram_id}/bays/{bay}/shelves/{shelf}/blocks", status_code=201)
def insert_block(planogram_id: str, bay: int, shelf: int, body: BlockIn, _: ManagerRole, ctx: Ctx) -> Planogram:
    """Inserts a Block on a Shelf (counted from the bottom) of a Draft."""
    return planograms.insert_block(ctx, planogram_id, bay, shelf, body.sku, body.facings, body.position)


@router.get("/planograms/{planogram_id}/bays/{bay}/blocks/{block_id}/crop", response_class=Response)
def block_crop(planogram_id: str, bay: int, block_id: str, _: AnyRole, ctx: Ctx) -> Response:
    """The part of the Shelf Photo the Block was extracted from."""
    return Response(planograms.block_crop(ctx, planogram_id, bay, block_id), media_type="image/jpeg")


@router.post("/planograms/{planogram_id}/bays/{bay}/blocks/{block_id}/resolve")
def resolve_unknown(planogram_id: str, bay: int, block_id: str, body: Resolution, _: ManagerRole, ctx: Ctx) -> Planogram:
    """Resolves an Unknown Product Block: creates a new Product from its crop, or adds the crop
    as a reference image of an existing Product. The Block becomes that Product."""
    return planograms.resolve_unknown(ctx, planogram_id, bay, block_id, body)


@router.post(
    "/planograms/{planogram_id}/approve",
    responses={409: {"description": "Not a Draft, or Unknown Products remain (listed in `unknown_blocks`)"}},
)
def approve(planogram_id: str, actor: ManagerRole, ctx: Ctx) -> Planogram:
    """Approves a Draft Planogram; the Fixture's previous Approved Planogram is Superseded."""
    return planograms.approve(ctx, planogram_id, actor)
