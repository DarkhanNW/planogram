"""The Recognizer seam (ADR 0001): Shelf Photo in, recognised Facings out. Extraction and the
Compliance Check depend only on this interface."""

from typing import Protocol

import numpy as np
from pydantic import BaseModel

from planogram.geometry import Box
from planogram.models import Product


class RecognizedFacing(BaseModel):
    box: Box
    shelf: int
    """The Shelf the Facing sits on, counted from the bottom (1 is the bottom Shelf)."""
    sku: str | None
    """The best-matching Product, or None for an Unknown Product."""
    confidence: float
    """How sure the Recognizer is of this Facing's identity (Product or Unknown Product), 0..1."""


class EmptyRegion(BaseModel):
    box: Box
    shelf: int
    confidence: float
    """How sure the Recognizer is that this Shelf space is empty, 0..1."""


class Recognition(BaseModel):
    facings: list[RecognizedFacing]
    empty_regions: list[EmptyRegion]


class Recognizer(Protocol):
    def recognize(self, image: np.ndarray, candidates: list[Product], fallback: list[Product]) -> Recognition:
        """Recognises the Facings and empty Shelf space in a BGR Shelf Photo of one Bay.

        Each Facing is matched against ``candidates`` first and against ``fallback`` only when
        no candidate matches, which keeps matching small (e.g. the Products of the Approved
        Planogram first, then the rest of the catalogue)."""
        ...
