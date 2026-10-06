"""Domain errors, mapped to HTTP responses in ``create_app``."""

from typing import Any


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    """The request is valid but the current state does not allow it."""

    status_code = 409


class Invalid(DomainError):
    status_code = 422
