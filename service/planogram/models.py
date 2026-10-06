from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from planogram.geometry import Box


class Store(BaseModel):
    id: str
    name: str


class Fixture(BaseModel):
    id: str
    store_id: str
    name: str
    bay_count: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bays(self) -> list[int]:
        return list(range(1, self.bay_count + 1))


class Input(BaseModel):
    """Request bodies reject unknown fields, so personal details can never slip in."""

    model_config = ConfigDict(extra="forbid")


class StoreIn(Input):
    name: str = Field(min_length=1, max_length=200)


class FixtureIn(Input):
    name: str = Field(min_length=1, max_length=200)
    bay_count: int = Field(ge=1, le=100)


class ReferenceImage(BaseModel):
    id: str
    sku: str
    image_key: str = Field(exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"/products/{self.sku}/reference-images/{self.id}"


class Product(BaseModel):
    sku: str
    name: str
    reference_images: list[ReferenceImage] = []


class ShelfPhoto(BaseModel):
    id: str
    store_id: str
    fixture_id: str
    bay: int
    uploaded_by: str
    uploaded_at: datetime
    width: int
    height: int
    image_key: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_url(self) -> str | None:
        """None once the photo has been deleted, on request or by the retention sweep."""
        return f"/shelf-photos/{self.id}/image" if self.image_key else None


class ImportFailure(BaseModel):
    row: int
    sku: str
    reason: str


class ImportReport(BaseModel):
    created: list[str]
    updated: list[str]
    failed: list[ImportFailure]


class Block(BaseModel):
    """A run of adjacent Facings of one Product (or an Unknown Product) on a Shelf."""

    id: str
    sku: str | None
    facings: int
    box: Box | None = None
    """Where the Block is in the Shelf Photo it was extracted from; None for inserted Blocks."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unknown(self) -> bool:
        return self.sku is None


class Shelf(BaseModel):
    number: int
    """Counted from the bottom: 1 is the bottom Shelf."""
    blocks: list[Block]
    """In order from the left."""


class BayLayout(BaseModel):
    bay: int
    shelf_photo_id: str | None
    shelves: list[Shelf]

    @property
    def skus(self) -> set[str]:
        """The Products planned in the Bay."""
        return {b.sku for s in self.shelves for b in s.blocks if b.sku is not None}


class PlanogramStatus(str, Enum):
    DRAFT = "Draft"
    APPROVED = "Approved"
    SUPERSEDED = "Superseded"


class Planogram(BaseModel):
    id: str
    fixture_id: str
    status: PlanogramStatus
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    superseded_at: datetime | None = None
    bays: list[BayLayout]

    def bay(self, number: int) -> BayLayout | None:
        return next((b for b in self.bays if b.bay == number), None)


class JobKind(str, Enum):
    EXTRACTION = "extraction"
    COMPLIANCE_CHECK = "compliance_check"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus
    shelf_photo_id: str
    submitted_by: str
    submitted_at: datetime
    result_id: str | None = None
    error: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def result_url(self) -> str | None:
        """The Draft Planogram or Compliance Check, once the job is done."""
        if self.result_id is None:
            return None
        collection = "planograms" if self.kind == JobKind.EXTRACTION else "compliance-checks"
        return f"/{collection}/{self.result_id}"


class ExtractionIn(Input):
    shelf_photo_id: str


class BlockChange(Input):
    sku: str | None = None
    """The Product the Block is; set it to resolve an Unknown Product or correct a match."""
    facings: int | None = Field(default=None, ge=1)


class NewProduct(Input):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class Resolution(Input):
    """How to resolve an Unknown Product: give exactly one of the two."""

    new_product: NewProduct | None = None
    """Create this Product, with the Block's crop as its reference image."""
    existing_sku: str | None = None
    """Add the Block's crop as a reference image of this existing Product."""

    @model_validator(mode="after")
    def exactly_one(self) -> "Resolution":
        if (self.new_product is None) == (self.existing_sku is None):
            raise ValueError("Give exactly one of new_product or existing_sku")
        return self


class BlockIn(Input):
    sku: str
    facings: int = Field(ge=1)
    position: int = Field(ge=0)
    """Where on the Shelf to insert the Block: 0 is the leftmost."""


class ComplianceCheckIn(Input):
    shelf_photo_id: str


class DeviationKind(str, Enum):
    GAP = "Gap"
    UNEXPECTED = "Unexpected"


class Position(BaseModel):
    """Where a Block sits: its Bay, its Shelf (from the bottom), its order from the left on
    that Shelf (1 is the leftmost) and its number of Facings."""

    bay: int
    shelf: int
    order: int
    facings: int


class Deviation(BaseModel):
    kind: DeviationKind
    sku: str | None
    """The planned Product for a Gap; what is on the Shelf for Unexpected (None for an Unknown Product)."""
    facings: int
    """How many Facings the Deviation involves."""
    planned: Position | None
    """The planned Block's Position; None for something not in the Approved Planogram."""
    observed: Position | None
    """The observed Block's Position; None when nothing of the planned Block is left."""
    box: Box
    """Where the Deviation is in the Shelf Photo."""
    confidence: float


class ComplianceCheck(BaseModel):
    id: str
    shelf_photo_id: str
    planogram_id: str
    """The Approved Planogram current for the Fixture when the check was submitted."""
    store_id: str
    fixture_id: str
    bay: int
    submitted_by: str
    submitted_at: datetime
    compliance_score: float
    """The percentage of the Bay's planned Facings present in their correct Position, as a fraction 0..1."""
    deviations: list[Deviation]
