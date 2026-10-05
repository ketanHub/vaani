from fastapi.testclient import TestClient


def test_ingested_knowledge_becomes_grounded(client: TestClient) -> None:
    before = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={
            "call_id": "rag-before",
            "text": "Do you have wheelchair parking?",
        },
    )
    assert before.status_code == 200
    assert before.json()["grounded"] is False

    ingest = client.post(
        "/v1/tenants/demo-clinic/knowledge/documents",
        json={
            "document_key": "parking-policy",
            "title": "Parking policy",
            "text": (
                "Do you have wheelchair parking? Yes. Wheelchair-accessible "
                "parking is available in basement level B1 beside the lift."
            ),
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["chunk_count"] == 1

    search = client.post(
        "/v1/tenants/demo-clinic/knowledge/search",
        json={"query": "wheelchair parking", "top_k": 3},
    )
    assert search.status_code == 200
    assert search.json()
    assert search.json()[0]["document_key"] == "parking-policy"

    after = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={
            "call_id": "rag-after",
            "text": "Do you have wheelchair parking?",
        },
    )
    assert after.status_code == 200
    data = after.json()
    assert data["grounded"] is True
    assert data["handoff_required"] is False
    assert data["source_ids"][0].startswith("knowledge:parking-policy:")
    assert "basement level B1" in data["reply"]


def test_document_upsert_replaces_old_chunks(client: TestClient) -> None:
    endpoint = "/v1/tenants/demo-clinic/knowledge/documents"
    first = client.post(
        endpoint,
        json={
            "document_key": "holiday-policy",
            "title": "Holiday policy",
            "text": "The clinic is closed on Diwali.",
        },
    )
    second = client.post(
        endpoint,
        json={
            "document_key": "holiday-policy",
            "title": "Updated holiday policy",
            "text": "The clinic is open on Diwali from 10 AM to 2 PM.",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    search = client.post(
        "/v1/tenants/demo-clinic/knowledge/search",
        json={"query": "Diwali", "top_k": 5},
    )
    contents = [
        item["content"]
        for item in search.json()
        if item["document_key"] == "holiday-policy"
    ]
    assert contents == ["The clinic is open on Diwali from 10 AM to 2 PM."]


def test_knowledge_rejects_unknown_tenant(client: TestClient) -> None:
    response = client.post(
        "/v1/tenants/not-a-tenant/knowledge/documents",
        json={
            "document_key": "x",
            "title": "X",
            "text": "Unknown tenant data.",
        },
    )
    assert response.status_code == 404
