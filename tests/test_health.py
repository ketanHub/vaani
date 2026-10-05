from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "redis": "disabled",
        "local_voice": "disabled",
        "calendar_provider": "memory",
        "notifications": "disabled",
    }


def test_demo_tenant_summary(client: TestClient) -> None:
    response = client.get("/v1/tenants/demo-clinic")
    assert response.status_code == 200
    assert response.json()["faq_count"] == 5
