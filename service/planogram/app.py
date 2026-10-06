from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from planogram.api import photos, products, stores
from planogram.blurring import OpenCvPersonBlurrer, PersonBlurrer
from planogram.context import Clock, Context
from planogram.images import LocalImageStore
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


def create_app(settings: Settings, blurrer: PersonBlurrer | None = None, clock: Clock = utc_now) -> FastAPI:
    ctx = Context(
        settings=settings,
        repo=Repository(settings.db_path),
        images=LocalImageStore(settings.image_dir),
        blurrer=blurrer or OpenCvPersonBlurrer(),
        clock=clock,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        ctx.repo.close()

    app = FastAPI(title="Planogram", version="0.1.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.context = ctx
    for module in (stores, products, photos):
        app.include_router(module.router)
    return app
