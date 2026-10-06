"""The labelled set: Shelf Photos, each with a hand-checked Planogram of the Bay it shows and
optionally a reference Planogram with the Deviations a Compliance Check against it should
report. The format is documented in README.md next to this file."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from planogram.models import DeviationKind

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabelledBlock(Label):
    sku: str | None
    """None for something not in the Product Catalogue: the right answer is an Unknown Product."""
    facings: int = Field(ge=1)


class LabelledShelf(Label):
    number: int = Field(ge=1)
    """Counted from the bottom: 1 is the bottom Shelf."""
    blocks: list[LabelledBlock]
    """In order from the left."""


class ExpectedDeviation(Label):
    kind: DeviationKind
    sku: str | None
    """The planned Product, or for Unexpected what is on the Shelf (None for an Unknown Product)."""
    shelf: int = Field(ge=1)
    """The planned Shelf; for Unexpected, the Shelf it was found on."""


class Reference(Label):
    shelves: list[LabelledShelf]
    """The Approved Planogram of the Bay to check the photo against."""
    deviations: list[ExpectedDeviation]
    """Every Deviation a Compliance Check against ``shelves`` should report; empty if none."""


class PhotoLabels(Label):
    smoke: bool = False
    """A smoke case runs through the pipeline to catch gross breakage but is left out of the
    metrics, e.g. the mock-up drinks Fixture image."""
    shelves: list[LabelledShelf] | None = None
    """The Bay as it stands in the photo; may be left out only for a smoke case."""
    reference: Reference | None = None


class Case(BaseModel):
    photo: Path
    labels: PhotoLabels


class LabelledSet(BaseModel):
    root: Path
    catalogue_csv: str
    catalogue_files: dict[str, bytes]
    cases: list[Case]


class InvalidSet(Exception):
    pass


def load_set(root: Path) -> LabelledSet:
    csv_path, catalogue_dir, photos_dir = root / "catalogue.csv", root / "catalogue", root / "photos"
    for required in (csv_path, photos_dir):
        if not required.exists():
            raise InvalidSet(f"{root}: missing {required.name}")
    files = {p.name: p.read_bytes() for p in sorted(catalogue_dir.iterdir()) if p.is_file()} if catalogue_dir.is_dir() else {}

    cases = []
    for photo in sorted(p for p in photos_dir.iterdir() if p.suffix.lower() in PHOTO_SUFFIXES):
        label_path = photo.with_suffix(".json")
        if not label_path.exists():
            raise InvalidSet(f"{photo}: no labels ({label_path.name})")
        try:
            labels = PhotoLabels.model_validate(json.loads(label_path.read_text(encoding="utf-8")))
        except ValueError as e:  # bad JSON, or labels not in the format
            raise InvalidSet(f"{label_path}: {e}") from e
        if labels.shelves is None and not labels.smoke:
            raise InvalidSet(f"{label_path}: \"shelves\" is required unless the photo is a smoke case")
        cases.append(Case(photo=photo, labels=labels))
    if not cases:
        raise InvalidSet(f"{photos_dir}: no Shelf Photos")
    return LabelledSet(root=root, catalogue_csv=csv_path.read_text(encoding="utf-8"), catalogue_files=files, cases=cases)
