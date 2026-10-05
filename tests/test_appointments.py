from fastapi.testclient import TestClient


def _booking_payload(request_id: str = "appt-1") -> dict[str, object]:
    return {
        "request_id": request_id,
        "call_id": "call-appointment-1",
        "customer_name": "Asha Sharma",
        "customer_phone": "+919999999999",
        "service": "General consultation",
        "starts_at": "2026-10-05T10:00:00+05:30",
        "duration_minutes": 45,
        "notes": "First visit",
    }


def test_book_appointment(client: TestClient) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/appointments",
        json=_booking_payload(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == "demo-clinic"
    assert data["request_id"] == "appt-1"
    assert data["status"] == "confirmed"
    assert data["external_event_id"] == "local-demo-clinic-appt-1"
    assert data["starts_at"] == "2026-10-05T10:00:00+05:30"
    assert data["ends_at"] == "2026-10-05T10:45:00+05:30"


def test_booking_is_idempotent_per_tenant(client: TestClient) -> None:
    first = client.post(
        "/v1/tenants/demo-clinic/appointments",
        json=_booking_payload("same-request"),
    )
    second_payload = _booking_payload("same-request")
    second_payload["service"] = "Changed service should not duplicate"
    second = client.post(
        "/v1/tenants/demo-clinic/appointments",
        json=second_payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["service"] == "General consultation"

    listed = client.get("/v1/tenants/demo-clinic/appointments")
    matching = [item for item in listed.json() if item["request_id"] == "same-request"]
    assert len(matching) == 1
    assert matching[0]["starts_at"] == "2026-10-05T10:00:00+05:30"
    assert matching[0]["ends_at"] == "2026-10-05T10:45:00+05:30"


def test_booking_rejects_unknown_tenant(client: TestClient) -> None:
    response = client.post(
        "/v1/tenants/not-a-tenant/appointments",
        json=_booking_payload(),
    )
    assert response.status_code == 404


def test_booking_rejects_naive_datetime(client: TestClient) -> None:
    payload = _booking_payload("naive-datetime")
    payload["starts_at"] = "2026-10-05T10:00:00"

    response = client.post(
        "/v1/tenants/demo-clinic/appointments",
        json=payload,
    )

    assert response.status_code == 422
    assert "timezone offset" in response.text
