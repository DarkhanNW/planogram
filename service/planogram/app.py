from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from planogram.api import jobs as jobs_api
from planogram.api import compliance, photos, planograms, products, stores
from planogram.blurring import OpenCvPersonBlurrer, PersonBlurrer
from planogram.context import Clock, Context
from planogram.errors import DomainError
from planogram.images import ImageStore, LocalImageStore
from planogram.jobs import JobRunner, ThreadJobRunner
from planogram.recognition import Recognizer
from planogram.repository import Repository
from planogram.settings import Settings

DESCRIPTION = """
Planogram service: Extraction of Draft Planograms from Shelf Photos and Compliance Checks
against Approved Planograms.

Every request needs the service API key (`X-API-Key`) and the acting user's opaque ID
(`X-User-Id`) and role (`X-User-Role`: Viewer, Operator or Manager).
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


def default_recognizer(settings: Settings, images: ImageStore) -> Recognizer:
    from planogram.vision import TwoStageRecognizer  # needs the optional vision dependencies

    return TwoStageRecognizer(settings, images)


def create_app(
    settings: Settings,
    blurrer: PersonBlurrer | None = None,
    recognizer: Recognizer | None = None,
    jobs: JobRunner | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    images = LocalImageStore(settings.image_dir)
    ctx = Context(
        settings=settings,
        repo=Repository(settings.db_path),
        images=images,
        blurrer=blurrer or OpenCvPersonBlurrer(),
        recognizer=recognizer or default_recognizer(settings, images),
        jobs=jobs or ThreadJobRunner(),
        clock=clock,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        ctx.jobs.shutdown()
        ctx.repo.close()

    app = FastAPI(title="Planogram", version="0.1.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.context = ctx

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, e: DomainError) -> JSONResponse:
        return JSONResponse({"detail": e.message, **e.details}, status_code=e.status_code)

    for module in (stores, products, photos, jobs_api, planograms, compliance):
        app.include_router(module.router)
    return app
