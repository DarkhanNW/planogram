import pytest
from fastapi.testclient import TestClient

from conftest import MANAGER, OPERATOR, VIEWER, import_catalogue, jpeg


def test_manager_imports_products_with_reference_images(client: TestClient) -> None:
    response = import_catalogue(
        client,
        "sku,name,images\nSKU-1,Aloe Vera Green,aloe-front.jpg;aloe-side.jpg\nSKU-2,Cola Zero,cola.jpg\n",
        {"aloe-front.jpg": jpeg(), "aloe-side.jpg": jpeg(), "cola.jpg": jpeg()},
    )
    assert response.status_code == 200
    assert response.json()["failed"] == []

    products = client.get("/products", headers=VIEWER).json()
    assert [(p["sku"], p["name"], len(p["reference_images"])) for p in products] == [
        ("SKU-1", "Aloe Vera Green", 2),
        ("SKU-2", "Cola Zero", 1),
    ]
    image_url = products[1]["reference_images"][0]["url"]
    image = client.get(image_url, headers=VIEWER)
    assert image.status_code == 200
    assert image.content == jpeg()


def test_reimporting_a_sku_renames_it_and_adds_its_images(client: TestClient) -> None:
    import_catalogue(client, "sku,name,images\nSKU-1,Aloe,a.jpg\n", {"a.jpg": jpeg()})
    response = import_catalogue(client, "sku,name,images\nSKU-1,Aloe Vera Green,b.jpg\n", {"b.jpg": jpeg()})

    assert response.json()["updated"] == ["SKU-1"]
    products = client.get("/products", headers=VIEWER).json()
    assert [(p["sku"], p["name"], len(p["reference_images"])) for p in products] == [
        ("SKU-1", "Aloe Vera Green", 2)
    ]


def test_reimport_without_images_only_renames(client: TestClient) -> None:
    import_catalogue(client, "sku,name,images\nSKU-1,Aloe,a.jpg\n", {"a.jpg": jpeg()})
    response = import_catalogue(client, "sku,name\nSKU-1,Aloe Vera Green\n", {})

    assert response.json() == {"created": [], "updated": ["SKU-1"], "failed": []}
    product = client.get("/products/SKU-1", headers=VIEWER).json()
    assert (product["name"], len(product["reference_images"])) == ("Aloe Vera Green", 1)


def test_import_reports_failed_rows_and_imports_the_valid_ones(client: TestClient) -> None:
    response = import_catalogue(
        client,
        "sku,name,images\n"
        "SKU-1,Aloe,a.jpg\n"
        "SKU-2,Cola,missing.jpg\n"
        "SKU-1,Aloe again,a.jpg\n"
        "SKU-3,No picture,\n"
        "SKU-4,Broken,broken.jpg\n",
        {"a.jpg": jpeg(), "broken.jpg": b"not an image"},
    )

    report = response.json()
    assert report["created"] == ["SKU-1"]
    assert [(f["row"], f["sku"], f["reason"]) for f in report["failed"]] == [
        (3, "SKU-2", "Missing image: missing.jpg"),
        (4, "SKU-1", "Duplicate SKU in the file"),
        (5, "SKU-3", "A new Product needs at least one reference image"),
        (6, "SKU-4", "Unreadable image: broken.jpg"),
    ]
    assert [p["sku"] for p in client.get("/products", headers=VIEWER).json()] == ["SKU-1"]


def test_csv_without_required_columns_is_rejected(client: TestClient) -> None:
    response = import_catalogue(client, "code,title\nSKU-1,Aloe\n", {})
    assert response.status_code == 422


@pytest.mark.parametrize("who", [VIEWER, OPERATOR])
def test_only_manager_imports(client: TestClient, who: dict[str, str]) -> None:
    response = import_catalogue(client, "sku,name,images\nSKU-1,Aloe,a.jpg\n", {"a.jpg": jpeg()}, who=who)
    assert response.status_code == 403
    assert client.get("/products", headers=MANAGER).json() == []
