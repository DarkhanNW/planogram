from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response

from planogram.access import AnyRole, ManagerRole, OperatorRole
from planogram.context import Context, get_context
from planogram.models import ShelfPhoto
from planogram.photos import delete_shelf_photo, get_shelf_photo, ingest_shelf_photo

router = APIRouter(tags=["Shelf Photos"])
Ctx = Annotated[Context, Depends(get_context)]


@router.post("/shelf-photos", status_code=201)
async def upload(
    image: UploadFile,
    store_id: Annotated[str, Form()],
    fixture_id: Annotated[str, Form()],
    bay: Annotated[int, Form()],
    actor: OperatorRole,
    ctx: Ctx,
) -> ShelfPhoto:
    """Uploads a Shelf Photo of one whole Bay. People in it are blurred before it is stored;
    the original is never kept."""
    return ingest_shelf_photo(ctx, store_id, fixture_id, bay, await image.read(), actor.user_id)


@router.get("/shelf-photos")
def list_shelf_photos(fixture_id: str, _: AnyRole, ctx: Ctx) -> list[ShelfPhoto]:
    return ctx.repo.list_shelf_photos(fixture_id)


@router.get("/shelf-photos/{photo_id}")
def get(photo_id: str, _: AnyRole, ctx: Ctx) -> ShelfPhoto:
    return get_shelf_photo(ctx, photo_id)


@router.get("/shelf-photos/{photo_id}/image", response_class=Response)
def get_image(photo_id: str, _: AnyRole, ctx: Ctx) -> Response:
    photo = get_shelf_photo(ctx, photo_id)
    if photo.image_key is None:
        raise HTTPException(404, "The Shelf Photo image has been deleted")
    return Response(ctx.images.get(photo.image_key), media_type="image/jpeg")


@router.delete("/shelf-photos/{photo_id}", status_code=204)
def delete(photo_id: str, _: ManagerRole, ctx: Ctx) -> None:
    delete_shelf_photo(ctx, get_shelf_photo(ctx, photo_id))
