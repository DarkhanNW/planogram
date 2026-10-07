"""Times are stored and compared in UTC."""

from datetime import UTC, datetime


def as_utc(t: datetime) -> datetime:
    """``t`` in UTC; a time without a zone is taken to be UTC already."""
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
