"""Planogram lifecycle: Draft (editable) → Approved (never changes) → Superseded."""

from planogram.access import Actor
from planogram.context import Context
from planogram.errors import Conflict, Invalid, NotFound
from planogram.geometry import Box
from planogram.models import Block, BayLayout, Planogram, PlanogramStatus, Resolution, Shelf
from planogram.photos import crop_shelf_photo, get_shelf_photo
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


# Draft edits. Each loads the Draft, changes one Shelf and saves it; Blocks of the same
# Product left side by side by an edit are merged, since together they are one Block.


def change_block(
    ctx: Context, planogram_id: str, bay: int, block_id: str, sku: str | None, facings: int | None
) -> Planogram:
    draft, layout = _draft_bay(ctx, planogram_id, bay)
    shelf, index = _find_block(layout, block_id)
    if sku is not None:
        _require_product(ctx, sku)
    block = shelf.blocks[index]
    shelf.blocks[index] = block.model_copy(
        update={"sku": sku if sku is not None else block.sku, "facings": facings or block.facings}
    )
    return _save(ctx, draft, layout, shelf)


def delete_block(ctx: Context, planogram_id: str, bay: int, block_id: str) -> Planogram:
    draft, layout = _draft_bay(ctx, planogram_id, bay)
    shelf, index = _find_block(layout, block_id)
    del shelf.blocks[index]
    return _save(ctx, draft, layout, shelf)


def insert_block(
    ctx: Context, planogram_id: str, bay: int, shelf_number: int, sku: str, facings: int, position: int
) -> Planogram:
    """Inserts a Block at ``position`` (0 is the leftmost) on a Shelf, adding the Shelf if new."""
    draft, layout = _draft_bay(ctx, planogram_id, bay)
    _require_product(ctx, sku)
    shelf = next((s for s in layout.shelves if s.number == shelf_number), None)
    if shelf is None:
        shelf = Shelf(number=shelf_number, blocks=[])
        layout.shelves = sorted(layout.shelves + [shelf], key=lambda s: s.number)
    shelf.blocks.insert(min(position, len(shelf.blocks)), Block(id=new_id(), sku=sku, facings=facings))
    return _save(ctx, draft, layout, shelf)


def block_crop(ctx: Context, planogram_id: str, bay: int, block_id: str) -> bytes:
    """The part of the Shelf Photo a Block was extracted from."""
    planogram = get_planogram(ctx, planogram_id)
    layout = planogram.bay(bay)
    if layout is None:
        raise NotFound(f"The Planogram has no Bay {bay}")
    shelf, index = _find_block(layout, block_id)
    box = shelf.blocks[index].box
    if box is None or layout.shelf_photo_id is None:
        raise NotFound("The Block was not extracted from a Shelf Photo")
    return crop_shelf_photo(ctx, get_shelf_photo(ctx, layout.shelf_photo_id), box)


def resolve_unknown(ctx: Context, planogram_id: str, bay: int, block_id: str, resolution: Resolution) -> Planogram:
    """Resolves an Unknown Product Block from the shelf itself: the crop of its one Facing
    becomes a reference image of a new or existing Product, and the Block becomes that Product."""
    draft, layout = _draft_bay(ctx, planogram_id, bay)
    shelf, index = _find_block(layout, block_id)
    block = shelf.blocks[index]
    if not block.unknown:
        raise Conflict("Only an Unknown Product can be resolved from its crop")
    if block.box is None or layout.shelf_photo_id is None:
        raise Conflict("The Block was not extracted from a Shelf Photo, so it has no crop")
    crop = crop_shelf_photo(ctx, get_shelf_photo(ctx, layout.shelf_photo_id), block.box)

    if resolution.new_product is not None:
        sku = resolution.new_product.sku
        if ctx.repo.get_product(sku) is not None:
            raise Conflict(f"A Product with SKU {sku} already exists; add the crop to it instead")
        ctx.repo.upsert_product(sku, resolution.new_product.name)
    else:
        sku = resolution.existing_sku or ""
        _require_product(ctx, sku)
    ctx.repo.add_reference_image(sku, ctx.images.put(crop))
    shelf.blocks[index] = block.model_copy(update={"sku": sku})
    return _save(ctx, draft, layout, shelf)


def approve(ctx: Context, planogram_id: str, actor: Actor) -> Planogram:
    """Approves a Draft, superseding the Fixture's previous Approved Planogram. Refused while
    any Block is an Unknown Product, since no Compliance Check could match it."""
    draft = _draft(ctx, planogram_id)
    unknown = [
        {"bay": layout.bay, "shelf": shelf.number, "position": position, "block_id": block.id}
        for layout in draft.bays
        for shelf in layout.shelves
        for position, block in enumerate(shelf.blocks)
        if block.unknown
    ]
    if unknown:
        raise Conflict("Resolve every Unknown Product before approving", unknown_blocks=unknown)
    if not draft.bays:
        raise Conflict("The Draft Planogram has no Bays")
    now = ctx.clock()
    previous = current_approved(ctx, draft.fixture_id)
    if previous is not None:
        ctx.repo.save_planogram(
            previous.model_copy(update={"status": PlanogramStatus.SUPERSEDED, "superseded_at": now})
        )
    approved = draft.model_copy(
        update={"status": PlanogramStatus.APPROVED, "approved_by": actor.user_id, "approved_at": now}
    )
    ctx.repo.save_planogram(approved)
    return approved


def _draft(ctx: Context, planogram_id: str) -> Planogram:
    planogram = get_planogram(ctx, planogram_id)
    if planogram.status != PlanogramStatus.DRAFT:
        raise Conflict(
            f"An {planogram.status.value} Planogram never changes; extract and approve a new one to change the layout"
        )
    return planogram


def _draft_bay(ctx: Context, planogram_id: str, bay: int) -> tuple[Planogram, BayLayout]:
    draft = _draft(ctx, planogram_id)
    layout = draft.bay(bay)
    if layout is None:
        raise NotFound(f"The Planogram has no Bay {bay}")
    return draft, layout


def _find_block(layout: BayLayout, block_id: str) -> tuple[Shelf, int]:
    for shelf in layout.shelves:
        for index, block in enumerate(shelf.blocks):
            if block.id == block_id:
                return shelf, index
    raise NotFound("Block not found")


def _require_product(ctx: Context, sku: str) -> None:
    if ctx.repo.get_product(sku) is None:
        raise Invalid(f"No Product with SKU {sku} in the Product Catalogue")


def _save(ctx: Context, draft: Planogram, layout: BayLayout, shelf: Shelf) -> Planogram:
    shelf.blocks = merge_neighbours(shelf.blocks)
    layout.shelves = [s for s in layout.shelves if s.blocks]
    ctx.repo.save_planogram(draft)
    return draft


def merge_neighbours(blocks: list[Block]) -> list[Block]:
    merged: list[Block] = []
    for block in blocks:
        last = merged[-1] if merged else None
        if last is not None and not block.unknown and block.sku == last.sku:
            boxes = [b for b in (last.box, block.box) if b is not None]
            merged[-1] = last.model_copy(
                update={"facings": last.facings + block.facings, "box": Box.union(boxes) if boxes else None}
            )
        else:
            merged.append(block)
    return merged
