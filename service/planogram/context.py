from dataclasses import dataclass

from fastapi import Request

from planogram.images import ImageStore
from planogram.repository import Repository
from planogram.settings import Settings


@dataclass
class Context:
    """Everything a request handler needs, wired once in ``create_app``."""

    settings: Settings
    repo: Repository
    images: ImageStore


def get_context(request: Request) -> Context:
    ctx: Context = request.app.state.context
    return ctx
