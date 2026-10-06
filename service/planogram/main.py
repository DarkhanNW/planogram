"""ASGI entrypoint: ``uvicorn planogram.main:app``. Configuration comes from the environment."""

from planogram.app import create_app
from planogram.settings import Settings

app = create_app(Settings.from_env())
