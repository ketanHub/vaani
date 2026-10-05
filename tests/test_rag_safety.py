from fastapi.testclient import TestClient


def _ingest_parking(client: TestClient) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/knowledge/documents",
        json={
            "document_key": "rag-safety-parking",
            "title": "Parking policy",
            "text": (
                "Do you have wheelchair parking? Yes. Wheelchair-accessible "
                "parking is available in basement level B1 beside the lift."
            ),
        },
    )
    assert response.status_code == 200


def test_unrelated_vector_hit_requires_handoff(
    client: TestClient,
) -> None:
    _ingest_parking(client)

    response = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={
            "call_id": "rag-safety-helipad",
            "text": "Do you have a rooftop helipad?",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["grounded"] is False
    assert data["handoff_required"] is True
    assert data["source_ids"] == []
    assert "verified information" in data["reply"]


def test_related_parking_paraphrase_stays_grounded(
    client: TestClient,
) -> None:
    _ingest_parking(client)

    response = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={
            "call_id": "rag-safety-related",
            "text": "Is wheelchair parking available?",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["grounded"] is True
    assert data["handoff_required"] is False
    assert data["source_ids"][0].startswith("knowledge:rag-safety-parking:")
