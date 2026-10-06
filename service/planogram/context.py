from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import Request

from planogram.blurring import PersonBlurrer
from planogram.images import ImageStore
from planogram.jobs import JobRunner
from planogram.recognition import Recognizer
from planogram.repository import Repository
from planogram.settings import Settings

Clock = Callable[[], datetime]


@dataclass
class Context:
    """Everything a request handler needs, wired once in ``create_app``."""

    settings: Settings
    repo: Repository
    images: ImageStore
    blurrer: PersonBlurrer
    recognizer: Recognizer
    jobs: JobRunner
    clock: Clock


def get_context(request: Request) -> Context:
    ctx: Context = request.app.state.context
    return ctx
