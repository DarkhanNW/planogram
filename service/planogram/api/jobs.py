from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from planogram.access import AnyRole, OperatorRole
from planogram.context import Context, get_context
from planogram.extraction import submit_extraction
from planogram.models import ExtractionIn, Job

router = APIRouter(tags=["Jobs"])
Ctx = Annotated[Context, Depends(get_context)]


@router.post("/extractions", status_code=202)
def extraction(body: ExtractionIn, actor: OperatorRole, ctx: Ctx) -> Job:
    """Submits a Shelf Photo for Extraction. Poll the returned job; when done, its
    `result_url` is the Fixture's Draft Planogram holding the extracted Bay."""
    return submit_extraction(ctx, body.shelf_photo_id, actor)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _: AnyRole, ctx: Ctx) -> Job:
    job = ctx.repo.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job
