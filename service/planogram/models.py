from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


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
