"""Image store: Shelf Photos, crops, reference images and Annotated Photos live here,
behind an interface so local files can be swapped for object storage."""

import uuid
from pathlib import Path
from typing import Protocol


class ImageStore(Protocol):
    def put(self, data: bytes, suffix: str = ".jpg") -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalImageStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, suffix: str = ".jpg") -> str:
        key = f"{uuid.uuid4().hex}{suffix}"
        (self._root / key).write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if path.parent != self._root.resolve():
            raise KeyError(key)
        return path
