from fastapi.testclient import TestClient

from conftest import API_KEY, MANAGER


def test_request_without_api_key_is_refused(client: TestClient) -> None:
    response = client.get("/stores", headers={"X-User-Id": "u1", "X-User-Role": "Viewer"})
    assert response.status_code == 401


def test_request_with_wrong_api_key_is_refused(client: TestClient) -> None:
    response = client.get(
        "/stores", headers={"X-API-Key": "nope", "X-User-Id": "u1", "X-User-Role": "Viewer"}
    )
    assert response.status_code == 401


def test_request_without_user_id_is_refused(client: TestClient) -> None:
    response = client.get("/stores", headers={"X-API-Key": API_KEY, "X-User-Role": "Viewer"})
    assert response.status_code == 401


def test_request_with_unknown_role_is_refused(client: TestClient) -> None:
    response = client.get(
        "/stores", headers={"X-API-Key": API_KEY, "X-User-Id": "u1", "X-User-Role": "Admin"}
    )
    assert response.status_code == 401


def test_email_address_is_refused_as_user_id(client: TestClient) -> None:
    response = client.get(
        "/stores",
        headers={"X-API-Key": API_KEY, "X-User-Id": "jo@example.com", "X-User-Role": "Viewer"},
    )
    assert response.status_code == 400


def test_openapi_schema_documents_the_api(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/stores" in schema["paths"]
