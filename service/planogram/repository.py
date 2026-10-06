"""SQLite repository. Domain code depends only on these methods, so the storage engine can
be swapped (e.g. Postgres) without touching it."""

import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from planogram.models import (
    ComplianceCheck,
    Fixture,
    Job,
    Planogram,
    PlanogramStatus,
    Product,
    ReferenceImage,
    ShelfPhoto,
    Store,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fixtures (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    bay_count INTEGER NOT NULL,
    created_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_images (
    id TEXT PRIMARY KEY,
    sku TEXT NOT NULL REFERENCES products(sku),
    image_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shelf_photos (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    fixture_id TEXT NOT NULL REFERENCES fixtures(id),
    bay INTEGER NOT NULL,
    uploaded_by TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    image_key TEXT
);
CREATE TABLE IF NOT EXISTS planograms (
    id TEXT PRIMARY KEY,
    fixture_id TEXT NOT NULL REFERENCES fixtures(id),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    document TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS planograms_by_fixture ON planograms(fixture_id, status);
CREATE TABLE IF NOT EXISTS compliance_checks (
    id TEXT PRIMARY KEY,
    fixture_id TEXT NOT NULL REFERENCES fixtures(id),
    bay INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    document TEXT NOT NULL,
    annotated_photo_key TEXT
);
CREATE INDEX IF NOT EXISTS compliance_checks_by_bay ON compliance_checks(fixture_id, bay, submitted_at);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL
);
"""


def new_id() -> str:
    return uuid.uuid4().hex


class Repository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.RLock()
        self._db.executescript(SCHEMA)
        self._add_missing_columns()

    def _add_missing_columns(self) -> None:
        """Columns added since a table was first created; CREATE TABLE IF NOT EXISTS skips them."""
        columns = {r["name"] for r in self._db.execute("PRAGMA table_info(compliance_checks)")}
        if "annotated_photo_key" not in columns:
            self._db.execute("ALTER TABLE compliance_checks ADD COLUMN annotated_photo_key TEXT")

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commits every write made inside the block together, or none of them if it raises.
        Other threads wait until it ends."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def _all(self, sql: str, *params: Any) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def _one(self, sql: str, *params: Any) -> sqlite3.Row | None:
        with self._lock:
            row: sqlite3.Row | None = self._db.execute(sql, params).fetchone()
            return row

    def _run(self, sql: str, *params: Any) -> None:
        with self._lock:
            self._db.execute(sql, params)

    # Stores and Fixtures

    def add_store(self, name: str, created_by: str) -> Store:
        store = Store(id=new_id(), name=name)
        self._run("INSERT INTO stores VALUES (?, ?, ?)", store.id, name, created_by)
        return store

    def list_stores(self) -> list[Store]:
        return [Store(id=r["id"], name=r["name"]) for r in self._all("SELECT * FROM stores ORDER BY name")]

    def get_store(self, store_id: str) -> Store | None:
        r = self._one("SELECT * FROM stores WHERE id = ?", store_id)
        return Store(id=r["id"], name=r["name"]) if r else None

    def add_fixture(self, store_id: str, name: str, bay_count: int, created_by: str) -> Fixture:
        fixture = Fixture(id=new_id(), store_id=store_id, name=name, bay_count=bay_count)
        self._run(
            "INSERT INTO fixtures VALUES (?, ?, ?, ?, ?)", fixture.id, store_id, name, bay_count, created_by
        )
        return fixture

    def list_fixtures(self, store_id: str) -> list[Fixture]:
        rows = self._all("SELECT * FROM fixtures WHERE store_id = ? ORDER BY name", store_id)
        return [_fixture(r) for r in rows]

    def get_fixture(self, fixture_id: str) -> Fixture | None:
        r = self._one("SELECT * FROM fixtures WHERE id = ?", fixture_id)
        return _fixture(r) if r else None

    # Product Catalogue

    def upsert_product(self, sku: str, name: str) -> bool:
        """Creates the Product or renames it; returns True when it was created."""
        with self._lock:
            existed = self._one("SELECT 1 FROM products WHERE sku = ?", sku) is not None
            if existed:
                self._run("UPDATE products SET name = ? WHERE sku = ?", name, sku)
            else:
                self._run("INSERT INTO products VALUES (?, ?)", sku, name)
            return not existed

    def add_reference_image(self, sku: str, image_key: str) -> ReferenceImage:
        image = ReferenceImage(id=new_id(), sku=sku, image_key=image_key)
        self._run("INSERT INTO reference_images VALUES (?, ?, ?)", image.id, sku, image_key)
        return image

    def list_products(self) -> list[Product]:
        products = {r["sku"]: Product(sku=r["sku"], name=r["name"]) for r in self._all("SELECT * FROM products ORDER BY sku")}
        for r in self._all("SELECT * FROM reference_images ORDER BY rowid"):
            products[r["sku"]].reference_images.append(_reference_image(r))
        return list(products.values())

    def get_product(self, sku: str) -> Product | None:
        r = self._one("SELECT * FROM products WHERE sku = ?", sku)
        if r is None:
            return None
        images = self._all("SELECT * FROM reference_images WHERE sku = ? ORDER BY rowid", sku)
        return Product(sku=r["sku"], name=r["name"], reference_images=[_reference_image(i) for i in images])

    # Shelf Photos

    def add_shelf_photo(self, photo: ShelfPhoto) -> None:
        self._run(
            "INSERT INTO shelf_photos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            photo.id, photo.store_id, photo.fixture_id, photo.bay, photo.uploaded_by,
            photo.uploaded_at.isoformat(), photo.width, photo.height, photo.image_key,
        )

    def get_shelf_photo(self, photo_id: str) -> ShelfPhoto | None:
        r = self._one("SELECT * FROM shelf_photos WHERE id = ?", photo_id)
        return _shelf_photo(r) if r else None

    def list_shelf_photos(self, fixture_id: str) -> list[ShelfPhoto]:
        rows = self._all("SELECT * FROM shelf_photos WHERE fixture_id = ? ORDER BY uploaded_at DESC", fixture_id)
        return [_shelf_photo(r) for r in rows]

    def clear_shelf_photo_image(self, photo_id: str) -> None:
        self._run("UPDATE shelf_photos SET image_key = NULL WHERE id = ?", photo_id)

    # Planograms: each is stored whole as a JSON document, indexed by Fixture and status.

    def save_planogram(self, planogram: Planogram) -> None:
        self._run(
            "INSERT OR REPLACE INTO planograms VALUES (?, ?, ?, ?, ?)",
            planogram.id, planogram.fixture_id, planogram.status.value,
            planogram.created_at.isoformat(), planogram.model_dump_json(),
        )

    def get_planogram(self, planogram_id: str) -> Planogram | None:
        r = self._one("SELECT document FROM planograms WHERE id = ?", planogram_id)
        return Planogram.model_validate_json(r["document"]) if r else None

    def list_planograms(self, fixture_id: str, status: PlanogramStatus | None = None) -> list[Planogram]:
        """Newest first."""
        sql = "SELECT document FROM planograms WHERE fixture_id = ?"
        params: list[Any] = [fixture_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        rows = self._all(sql + " ORDER BY created_at DESC, rowid DESC", *params)
        return [Planogram.model_validate_json(r["document"]) for r in rows]

    # Compliance Checks: each is stored whole as a JSON document, indexed by Bay and time.

    def save_compliance_check(self, check: ComplianceCheck) -> None:
        self._run(
            "INSERT OR REPLACE INTO compliance_checks VALUES (?, ?, ?, ?, ?, ?)",
            check.id, check.fixture_id, check.bay, check.submitted_at.isoformat(), check.model_dump_json(),
            check.annotated_photo_key,
        )

    def get_compliance_check(self, check_id: str) -> ComplianceCheck | None:
        r = self._one("SELECT document, annotated_photo_key FROM compliance_checks WHERE id = ?", check_id)
        if r is None:
            return None
        check = ComplianceCheck.model_validate_json(r["document"])
        check.annotated_photo_key = r["annotated_photo_key"]
        return check

    def clear_annotated_photos(self, shelf_photo_id: str) -> list[str]:
        """Forgets the Annotated Photos of every Compliance Check of the Shelf Photo; returns their keys."""
        where = "json_extract(document, '$.shelf_photo_id') = ? AND annotated_photo_key IS NOT NULL"
        with self.transaction():
            rows = self._all(f"SELECT annotated_photo_key FROM compliance_checks WHERE {where}", shelf_photo_id)
            self._run(f"UPDATE compliance_checks SET annotated_photo_key = NULL WHERE {where}", shelf_photo_id)
        return [r["annotated_photo_key"] for r in rows]

    # Jobs

    def save_job(self, job: Job) -> None:
        self._run("INSERT OR REPLACE INTO jobs VALUES (?, ?)", job.id, job.model_dump_json())

    def get_job(self, job_id: str) -> Job | None:
        r = self._one("SELECT document FROM jobs WHERE id = ?", job_id)
        return Job.model_validate_json(r["document"]) if r else None


def _shelf_photo(r: sqlite3.Row) -> ShelfPhoto:
    return ShelfPhoto(
        id=r["id"], store_id=r["store_id"], fixture_id=r["fixture_id"], bay=r["bay"],
        uploaded_by=r["uploaded_by"], uploaded_at=datetime.fromisoformat(r["uploaded_at"]),
        width=r["width"], height=r["height"], image_key=r["image_key"],
    )


def _reference_image(r: sqlite3.Row) -> ReferenceImage:
    return ReferenceImage(id=r["id"], sku=r["sku"], image_key=r["image_key"])


def _fixture(r: sqlite3.Row) -> Fixture:
    return Fixture(id=r["id"], store_id=r["store_id"], name=r["name"], bay_count=r["bay_count"])
