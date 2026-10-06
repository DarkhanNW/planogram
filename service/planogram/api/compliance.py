from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from planogram.access import AnyRole, OperatorRole
from planogram.compliance import annotated_photo_bytes, get_compliance_check, submit_compliance_check
from planogram.context import Context, get_context
from planogram.models import ComplianceCheck, ComplianceCheckIn, Job

router = APIRouter(tags=["Compliance Checks"])
Ctx = Annotated[Context, Depends(get_context)]


@router.post(
    "/compliance-checks",
    status_code=202,
    responses={409: {"description": "The Bay has no Approved Planogram, or the photo has been deleted"}},
)
def submit(body: ComplianceCheckIn, actor: OperatorRole, ctx: Ctx) -> Job:
    """Submits a Shelf Photo for a Compliance Check against the Approved Planogram current for
    its Fixture now. Poll the returned job; when done, its `result_url` is the Compliance Check."""
    return submit_compliance_check(ctx, body.shelf_photo_id, actor)


@router.get("/compliance-checks/{check_id}")
def get(check_id: str, _: AnyRole, ctx: Ctx) -> ComplianceCheck:
    return get_compliance_check(ctx, check_id)


@router.get("/compliance-checks/{check_id}/annotated-photo", response_class=Response)
def get_annotated_photo(check_id: str, _: AnyRole, ctx: Ctx) -> Response:
    """The Shelf Photo with every Deviation outlined and labelled by kind, and Unverified areas
    shaded lightly. Gone once the Shelf Photo is deleted."""
    return Response(annotated_photo_bytes(ctx, get_compliance_check(ctx, check_id)), media_type="image/jpeg")
