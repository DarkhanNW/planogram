"""Extraction: builds the Draft Planogram for a Bay from a Shelf Photo of it as it stands."""

from planogram.access import Actor
from planogram.context import Context
from planogram.errors import Conflict
from planogram.jobs import new_job, start_job
from planogram.layout import build_layout, to_shelves
from planogram.models import BayLayout, Job, JobKind, ShelfPhoto
from planogram.photos import get_shelf_photo, load_shelf_photo_image
from planogram.planograms import open_draft, with_bay


def submit_extraction(ctx: Context, shelf_photo_id: str, actor: Actor) -> Job:
    photo = get_shelf_photo(ctx, shelf_photo_id)
    if photo.image_key is None:
        raise Conflict("The Shelf Photo image has been deleted")
    job = new_job(JobKind.EXTRACTION, photo.id, actor.user_id, ctx.clock())
    return start_job(ctx.repo, ctx.jobs, job, lambda: extract(ctx, photo))


def extract(ctx: Context, photo: ShelfPhoto) -> str:
    """Puts the extracted Bay into the Fixture's Draft Planogram and returns the Draft's id."""
    recognition = ctx.recognizer.recognize(load_shelf_photo_image(ctx, photo), ctx.repo.list_products(), [])
    layout = BayLayout(bay=photo.bay, shelf_photo_id=photo.id, shelves=to_shelves(build_layout(recognition)))
    draft = with_bay(open_draft(ctx, photo.fixture_id), layout)
    ctx.repo.save_planogram(draft)
    return draft.id
