"""SQLite repository. Domain code depends only on these methods, so the storage engine can
be swapped (e.g. Postgres) without touching it."""

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from planogram.models import Fixture, Product, ReferenceImage, Store

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

    def close(self) -> None:
        self._db.close()

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


def _reference_image(r: sqlite3.Row) -> ReferenceImage:
    return ReferenceImage(id=r["id"], sku=r["sku"], image_key=r["image_key"])


def _fixture(r: sqlite3.Row) -> Fixture:
    return Fixture(id=r["id"], store_id=r["store_id"], name=r["name"], bay_count=r["bay_count"])
