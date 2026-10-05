from fastapi.testclient import TestClient


def _turn(
    client: TestClient,
    call_id: str,
    text: str,
) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={"call_id": call_id, "text": text},
    )
    assert response.status_code == 200


def test_dashboard_aggregates_tenant_activity(
    client: TestClient,
) -> None:
    initial = client.get("/v1/tenants/demo-clinic/dashboard/summary")
    assert initial.status_code == 200
    assert initial.json()["turns"] == 0

    _turn(
        client,
        "dashboard-grounded",
        "What are your opening hours?",
    )
    _turn(
        client,
        "dashboard-handoff",
        "Do you have a rooftop helipad?",
    )

    appointment = client.post(
        "/v1/tenants/demo-clinic/appointments",
        json={
            "request_id": "dashboard-appt",
            "call_id": "dashboard-grounded",
            "customer_name": "Asha Sharma",
            "customer_phone": "+919999999999",
            "service": "General consultation",
            "starts_at": "2026-10-06T10:00:00+05:30",
            "duration_minutes": 30,
        },
    )
    assert appointment.status_code == 200

    knowledge = client.post(
        "/v1/tenants/demo-clinic/knowledge/documents",
        json={
            "document_key": "dashboard-knowledge",
            "title": "Dashboard knowledge",
            "text": "A synthetic knowledge document for dashboard testing.",
        },
    )
    assert knowledge.status_code == 200

    completed = client.post(
        ("/v1/tenants/demo-clinic/calls/dashboard-grounded/complete"),
        json={
            "transcript": "Caller asked for clinic opening hours.",
            "caller_name": "Asha Sharma",
            "caller_phone": "+919999999999",
            "interest": "General consultation",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["lead_captured"] is True

    response = client.get("/v1/tenants/demo-clinic/dashboard/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["tenant_id"] == "demo-clinic"
    assert data["calls"] == 2
    assert data["turns"] == 2
    assert data["grounded_turns"] == 1
    assert data["handoff_turns"] == 1
    assert data["appointments"] == 1
    assert data["leads"] == 1
    assert data["completed_calls"] == 1
    assert data["knowledge_documents"] == 1
    assert data["notification_pending"] == 1
    assert data["notification_retry"] == 0
    assert data["notification_sent"] == 0
    assert data["notification_failed"] == 0
    assert data["average_processing_ms"] >= 0
    assert data["channels"]["text_http"]["turns"] == 2
    assert data["channels"]["text_http"]["average_processing_ms"] >= 0


def test_dashboard_rejects_unknown_tenant(
    client: TestClient,
) -> None:
    response = client.get("/v1/tenants/not-a-tenant/dashboard/summary")
    assert response.status_code == 404
