from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from planogram.access import AnyRole, ManagerRole
from planogram.catalogue import import_catalogue
from planogram.context import Context, get_context
from planogram.models import ImportReport, Product

router = APIRouter(tags=["Product Catalogue"])
Ctx = Annotated[Context, Depends(get_context)]


@router.post("/products/import")
async def bulk_import(
    csv: UploadFile, _: ManagerRole, ctx: Ctx, images: list[UploadFile] | None = None
) -> ImportReport:
    """Imports Products from a CSV with columns `sku`, `name` and `images` (reference image
    file names separated by `;`) plus the image files. Existing SKUs are renamed and gain the
    new images. Invalid rows are reported and skipped; valid rows are still imported."""
    files = {f.filename or "": await f.read() for f in images or []}
    try:
        text = (await csv.read()).decode("utf-8-sig")
        return import_catalogue(ctx.repo, ctx.images, text, files)
    except (UnicodeDecodeError, ValueError) as e:
        raise HTTPException(422, str(e))


@router.get("/products")
def list_products(_: AnyRole, ctx: Ctx) -> list[Product]:
    return ctx.repo.list_products()


@router.get("/products/{sku}")
def get_product(sku: str, _: AnyRole, ctx: Ctx) -> Product:
    product = ctx.repo.get_product(sku)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/products/{sku}/reference-images/{image_id}", response_class=Response)
def get_reference_image(sku: str, image_id: str, _: AnyRole, ctx: Ctx) -> Response:
    product = ctx.repo.get_product(sku)
    image = next((i for i in product.reference_images if i.id == image_id), None) if product else None
    if image is None:
        raise HTTPException(404, "Reference image not found")
    return Response(ctx.images.get(image.image_key), media_type=media_type(image.image_key))


def media_type(key: str) -> str:
    return "image/png" if key.endswith(".png") else "image/jpeg"
