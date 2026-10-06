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
