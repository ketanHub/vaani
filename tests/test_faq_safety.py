from fastapi.testclient import TestClient


def test_noisy_hindi_services_does_not_misroute_to_location(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={
            "call_id": "faq-noisy-services",
            "text": "क्या से बाई है?",
            "language": "hi",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["grounded"] is True
    assert data["handoff_required"] is False
    assert data["source_ids"] == ["services"]


def test_exact_hindi_services_stays_grounded(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={
            "call_id": "faq-exact-services",
            "text": "क्या सेवाएं हैं?",
            "language": "hi",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["grounded"] is True
    assert data["handoff_required"] is False
    assert data["source_ids"] == ["services"]


def test_hindi_function_words_alone_do_not_ground(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/turn",
        json={
            "call_id": "faq-function-words",
            "text": "क्या है?",
            "language": "hi",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["grounded"] is False
    assert data["handoff_required"] is True
    assert data["source_ids"] == []
