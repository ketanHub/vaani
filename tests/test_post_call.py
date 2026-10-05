from fastapi.testclient import TestClient


def _turn(client: TestClient, call_id: str, text: str) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={"call_id": call_id, "text": text},
    )
    assert response.status_code == 200


def test_complete_call_persists_summary_and_lead(client: TestClient) -> None:
    call_id = "post-call-1"
    _turn(client, call_id, "fees kitni hai")
    _turn(client, call_id, "Do you have parking?")

    response = client.post(
        f"/v1/tenants/demo-clinic/calls/{call_id}/complete",
        json={
            "transcript": "Caller asked about fees and parking. Wants a consultation.",
            "caller_name": "Asha Sharma",
            "caller_phone": "+919999999999",
            "interest": "General consultation",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == "demo-clinic"
    assert data["call_id"] == call_id
    assert data["turn_count"] == 2
    assert data["handoff_required"] is True
    assert data["lead_captured"] is True
    assert data["lead_id"]

    transient = client.get(f"/v1/tenants/demo-clinic/calls/{call_id}/state")
    assert transient.status_code == 404


def test_complete_call_is_idempotent(client: TestClient) -> None:
    call_id = "post-call-idempotent"
    _turn(client, call_id, "What are your opening hours?")

    first = client.post(
        f"/v1/tenants/demo-clinic/calls/{call_id}/complete",
        json={
            "transcript": "Caller asked for opening hours.",
            "caller_phone": "+918888888888",
        },
    )
    second = client.post(
        f"/v1/tenants/demo-clinic/calls/{call_id}/complete",
        json={
            "transcript": "This changed transcript must not overwrite the result.",
            "caller_phone": "+917777777777",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["summary"] == first.json()["summary"]
    assert second.json()["lead_id"] == first.json()["lead_id"]


def test_complete_call_without_phone_does_not_create_lead(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/calls/no-phone/complete",
        json={"transcript": "Caller only requested business hours."},
    )

    assert response.status_code == 200
    assert response.json()["lead_captured"] is False
    assert response.json()["lead_id"] is None


def test_complete_call_rejects_unknown_tenant(client: TestClient) -> None:
    response = client.post(
        "/v1/tenants/not-a-tenant/calls/test/complete",
        json={"transcript": "Test transcript"},
    )
    assert response.status_code == 404
