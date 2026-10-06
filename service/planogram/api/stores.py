from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from planogram.access import AnyRole, ManagerRole
from planogram.context import Context, get_context
from planogram.models import Fixture, FixtureIn, Store, StoreIn

router = APIRouter(tags=["Stores and Fixtures"])
Ctx = Annotated[Context, Depends(get_context)]


@router.post("/stores", status_code=201)
def register_store(body: StoreIn, actor: ManagerRole, ctx: Ctx) -> Store:
    return ctx.repo.add_store(body.name, actor.user_id)


@router.get("/stores")
def list_stores(_: AnyRole, ctx: Ctx) -> list[Store]:
    return ctx.repo.list_stores()


@router.post("/stores/{store_id}/fixtures", status_code=201)
def register_fixture(store_id: str, body: FixtureIn, actor: ManagerRole, ctx: Ctx) -> Fixture:
    if ctx.repo.get_store(store_id) is None:
        raise HTTPException(404, "Store not found")
    return ctx.repo.add_fixture(store_id, body.name, body.bay_count, actor.user_id)


@router.get("/stores/{store_id}/fixtures")
def list_fixtures(store_id: str, _: AnyRole, ctx: Ctx) -> list[Fixture]:
    if ctx.repo.get_store(store_id) is None:
        raise HTTPException(404, "Store not found")
    return ctx.repo.list_fixtures(store_id)


@router.get("/fixtures/{fixture_id}")
def get_fixture(fixture_id: str, _: AnyRole, ctx: Ctx) -> Fixture:
    fixture = ctx.repo.get_fixture(fixture_id)
    if fixture is None:
        raise HTTPException(404, "Fixture not found")
    return fixture
