"""Shelf Photo ingest (ADR 0003): the uploaded image is decoded in memory, people are
blurred, and only the blurred image is ever written to storage."""

import cv2
import numpy as np

from planogram.blurring import blur_people
from planogram.context import Context
from planogram.errors import Conflict, Invalid, NotFound
from planogram.models import ShelfPhoto
from planogram.repository import new_id


def decode_image(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise Invalid("The file is not a readable image")
    return image


def encode_jpeg(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise Invalid("The image could not be encoded")
    return encoded.tobytes()


def ingest_shelf_photo(ctx: Context, store_id: str, fixture_id: str, bay: int, data: bytes, uploaded_by: str) -> ShelfPhoto:
    fixture = ctx.repo.get_fixture(fixture_id)
    if fixture is None or fixture.store_id != store_id:
        raise Invalid("The Fixture is not in that Store")
    if bay not in fixture.bays:
        raise Invalid(f"{fixture.name} has Bays {fixture.bays[0]} to {fixture.bays[-1]}")

    original = decode_image(data)
    blurred = blur_people(original, ctx.blurrer.find_people(original))
    del original
    height, width = blurred.shape[:2]
    photo = ShelfPhoto(
        id=new_id(), store_id=store_id, fixture_id=fixture_id, bay=bay, uploaded_by=uploaded_by,
        uploaded_at=ctx.clock(), width=width, height=height, image_key=ctx.images.put(encode_jpeg(blurred)),
    )
    ctx.repo.add_shelf_photo(photo)
    return photo


def get_shelf_photo(ctx: Context, photo_id: str) -> ShelfPhoto:
    photo = ctx.repo.get_shelf_photo(photo_id)
    if photo is None:
        raise NotFound("Shelf Photo not found")
    return photo


def shelf_photo_bytes(ctx: Context, photo: ShelfPhoto) -> bytes:
    if photo.image_key is None:
        raise Conflict("The Shelf Photo image has been deleted")
    return ctx.images.get(photo.image_key)


def load_shelf_photo_image(ctx: Context, photo: ShelfPhoto) -> np.ndarray:
    return decode_image(shelf_photo_bytes(ctx, photo))


def delete_shelf_photo(ctx: Context, photo: ShelfPhoto) -> None:
    """Deletes the image; the record stays so Planograms and Compliance Checks keep their history."""
    if photo.image_key:
        ctx.images.delete(photo.image_key)
    ctx.repo.clear_shelf_photo_image(photo.id)
