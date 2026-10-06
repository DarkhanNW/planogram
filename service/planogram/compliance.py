"""Compliance Check: compares a Shelf Photo of a Bay with the Approved Planogram current for
its Fixture when the check is submitted."""

from planogram.access import Actor
from planogram.annotation import annotate
from planogram.comparer import compare
from planogram.context import Context
from planogram.errors import Conflict, NotFound
from planogram.jobs import new_job, start_job
from planogram.layout import build_layout
from planogram.models import ComplianceCheck, Job, JobKind, Planogram, ShelfPhoto
from planogram.photos import encode_jpeg, get_shelf_photo, load_shelf_photo_image
from planogram.planograms import current_approved
from planogram.repository import new_id


def submit_compliance_check(ctx: Context, shelf_photo_id: str, actor: Actor) -> Job:
    photo = get_shelf_photo(ctx, shelf_photo_id)
    if photo.image_key is None:
        raise Conflict("The Shelf Photo image has been deleted")
    # Bound now, so a Planogram approved while the job waits does not apply retroactively.
    planogram = current_approved(ctx, photo.fixture_id)
    if planogram is None or planogram.bay(photo.bay) is None:
        raise Conflict(f"Bay {photo.bay} has no Approved Planogram to check against")
    job = new_job(JobKind.COMPLIANCE_CHECK, photo.id, actor.user_id, ctx.clock())
    return start_job(ctx.repo, ctx.jobs, job, lambda: run_compliance_check(ctx, photo, planogram, job))


def run_compliance_check(ctx: Context, photo: ShelfPhoto, planogram: Planogram, job: Job) -> str:
    """Runs the Compliance Check, saves it and returns its id."""
    planned = planogram.bay(photo.bay)
    assert planned is not None
    planned_skus = planned.skus
    products = ctx.repo.list_products()
    image = load_shelf_photo_image(ctx, photo)
    recognition = ctx.recognizer.recognize(
        image,
        [p for p in products if p.sku in planned_skus],
        [p for p in products if p.sku not in planned_skus],
    )
    comparison = compare(planned, build_layout(recognition), ctx.settings.verification_threshold)
    annotated = annotate(image, comparison.deviations, comparison.unverified)
    result = ComplianceCheck(
        id=new_id(), shelf_photo_id=photo.id, planogram_id=planogram.id, store_id=photo.store_id,
        fixture_id=photo.fixture_id, bay=photo.bay, submitted_by=job.submitted_by, submitted_at=job.submitted_at,
        compliance_score=comparison.compliance_score, coverage=comparison.coverage,
        deviations=comparison.deviations, unverified=comparison.unverified,
        annotated_photo_key=ctx.images.put(encode_jpeg(annotated)),
    )
    ctx.repo.save_compliance_check(result)
    return result.id


def get_compliance_check(ctx: Context, check_id: str) -> ComplianceCheck:
    result = ctx.repo.get_compliance_check(check_id)
    if result is None:
        raise NotFound("Compliance Check not found")
    return result


def annotated_photo_bytes(ctx: Context, check: ComplianceCheck) -> bytes:
    if check.annotated_photo_key is None:
        raise NotFound("The Annotated Photo has been deleted with its Shelf Photo")
    return ctx.images.get(check.annotated_photo_key)
