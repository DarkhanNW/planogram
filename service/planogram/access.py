"""Access model: the host backend authenticates with the service API key and names the
acting user by opaque ID and role on every request. The service keeps no user records."""

import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException, Request


class Role(str, Enum):
    VIEWER = "Viewer"
    OPERATOR = "Operator"
    MANAGER = "Manager"


_RANK = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.MANAGER: 2}


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: Role


def current_actor(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
    x_user_role: Annotated[str | None, Header()] = None,
) -> Actor:
    expected = request.app.state.context.settings.api_key
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, "A valid service API key is required")
    if not x_user_id:
        raise HTTPException(401, "X-User-Id is required")
    if "@" in x_user_id:
        raise HTTPException(400, "X-User-Id must be the host's opaque user ID, not an email address")
    try:
        role = Role(x_user_role)
    except ValueError:
        raise HTTPException(401, "X-User-Role must be Viewer, Operator or Manager")
    return Actor(user_id=x_user_id, role=role)


def require(minimum: Role) -> Callable[[Actor], Actor]:
    """Dependency allowing ``minimum`` and every role above it."""

    def check(actor: Annotated[Actor, Depends(current_actor)]) -> Actor:
        if _RANK[actor.role] < _RANK[minimum]:
            raise HTTPException(403, f"{minimum.value} role required")
        return actor

    return check


AnyRole = Annotated[Actor, Depends(require(Role.VIEWER))]
OperatorRole = Annotated[Actor, Depends(require(Role.OPERATOR))]
ManagerRole = Annotated[Actor, Depends(require(Role.MANAGER))]
