"""Retention (ADR 0003): Shelf Photos are deleted a set number of months after upload, with their
Annotated Photos. Planograms and Compliance Checks are kept, and stay readable without them."""

import asyncio
import calendar
import logging
from datetime import datetime

from planogram.context import Context
from planogram.photos import delete_shelf_photo

log = logging.getLogger(__name__)


def months_before(t: datetime, months: int) -> datetime:
    """``t`` the given number of calendar months earlier, on the last day of the month when that
    month is too short (31 August less six months is 28 February)."""
    year, month = divmod(t.year * 12 + t.month - 1 - months, 12)
    month += 1
    return t.replace(year=year, month=month, day=min(t.day, calendar.monthrange(year, month)[1]))


def sweep_expired_shelf_photos(ctx: Context) -> int:
    """Deletes every Shelf Photo uploaded at least the retention period ago; returns how many."""
    cutoff = months_before(ctx.clock(), ctx.settings.photo_retention_months)
    expired = ctx.repo.list_shelf_photos_with_image_uploaded_before(cutoff)
    for photo in expired:
        delete_shelf_photo(ctx, photo)
    if expired:
        log.info("Retention sweep deleted %d Shelf Photos uploaded before %s", len(expired), cutoff.isoformat())
    return len(expired)


async def sweep_periodically(ctx: Context) -> None:
    """Sweeps every ``retention_sweep_hours`` until cancelled; a failed sweep is retried next time."""
    while True:
        await asyncio.sleep(ctx.settings.retention_sweep_hours * 3600)
        try:
            await asyncio.to_thread(sweep_expired_shelf_photos, ctx)
        except Exception:
            log.exception("Retention sweep failed")
