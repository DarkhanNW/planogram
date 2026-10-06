"""Product Catalogue bulk import: a CSV of SKUs and names (with the file names of each
Product's reference images) plus the image files themselves. Rows are upserted by SKU."""

import csv
import io
from collections.abc import Mapping
from pathlib import PurePath

import cv2
import numpy as np

from planogram.images import ImageStore
from planogram.models import ImportFailure, ImportReport
from planogram.repository import Repository

IMAGE_SEPARATOR = ";"


def is_readable_image(data: bytes) -> bool:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) is not None


def import_catalogue(repo: Repository, images: ImageStore, csv_text: str, files: Mapping[str, bytes]) -> ImportReport:
    report = ImportReport(created=[], updated=[], failed=[])
    seen: set[str] = set()
    reader = csv.DictReader(io.StringIO(csv_text))
    missing_columns = {"sku", "name"} - set(reader.fieldnames or [])
    if missing_columns:
        raise ValueError(f"CSV is missing column(s): {', '.join(sorted(missing_columns))}")

    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        sku = (row.get("sku") or "").strip()
        name = (row.get("name") or "").strip()
        image_names = [n.strip() for n in (row.get("images") or "").split(IMAGE_SEPARATOR) if n.strip()]

        def fail(reason: str) -> None:
            report.failed.append(ImportFailure(row=row_number, sku=sku, reason=reason))

        if not sku or not name:
            fail("SKU and name are required")
            continue
        if sku in seen:
            fail("Duplicate SKU in the file")
            continue
        seen.add(sku)
        absent = [n for n in image_names if n not in files]
        if absent:
            fail(f"Missing image: {', '.join(absent)}")
            continue
        unreadable = [n for n in image_names if not is_readable_image(files[n])]
        if unreadable:
            fail(f"Unreadable image: {', '.join(unreadable)}")
            continue
        if not image_names and repo.get_product(sku) is None:
            fail("A new Product needs at least one reference image")
            continue

        created = repo.upsert_product(sku, name)
        for image_name in image_names:
            key = images.put(files[image_name], PurePath(image_name).suffix.lower() or ".jpg")
            repo.add_reference_image(sku, key)
        (report.created if created else report.updated).append(sku)
    return report
