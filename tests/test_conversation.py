from fastapi.testclient import TestClient


def _turn(client: TestClient, text: str, call_id: str = "call-1"):
    return client.post(
        "/v1/tenants/demo-clinic/turn",
        json={"call_id": call_id, "text": text},
    )


def test_known_faq_is_grounded(client: TestClient) -> None:
    data = _turn(client, "What are your opening hours?").json()
    assert data["grounded"] is True
    assert data["handoff_required"] is False
    assert data["source_ids"] == ["hours"]


def test_hinglish_is_detected(client: TestClient) -> None:
    data = _turn(client, "timing kya hai").json()
    assert data["language"] == "hinglish"
    assert data["grounded"] is True


def test_unknown_fact_requires_handoff(client: TestClient) -> None:
    data = _turn(client, "Do you have parking?").json()
    assert data["grounded"] is False
    assert data["handoff_required"] is True
    assert data["source_ids"] == []


def test_turn_updates_tenant_scoped_call_state(client: TestClient) -> None:
    _turn(client, "What are your opening hours?", call_id="state-1")
    _turn(client, "Do you have parking?", call_id="state-1")

    response = client.get("/v1/tenants/demo-clinic/calls/state-1/state")
    assert response.status_code == 200
    assert response.json() == {
        "call_id": "state-1",
        "tenant_id": "demo-clinic",
        "language": "en",
        "turn_count": 2,
        "handoff_required": True,
    }


def test_call_state_does_not_cross_tenants(client: TestClient) -> None:
    _turn(client, "What are your opening hours?", call_id="shared-id")

    response = client.get("/v1/tenants/other-tenant/calls/shared-id/state")
    assert response.status_code == 404
