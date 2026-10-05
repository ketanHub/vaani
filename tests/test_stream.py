from fastapi.testclient import TestClient


def test_websocket_turn(client: TestClient) -> None:
    with client.websocket_connect("/v1/media/demo-clinic/ws-1") as websocket:
        websocket.send_json({"text": "fees kitni hai"})
        data = websocket.receive_json()

    assert data["type"] == "assistant_turn"
    assert data["language"] == "hinglish"
    assert data["grounded"] is True
    assert data["source_ids"] == ["fee"]


def test_websocket_rejects_empty_turn(client: TestClient) -> None:
    with client.websocket_connect("/v1/media/demo-clinic/ws-2") as websocket:
        websocket.send_json({"text": ""})
        data = websocket.receive_json()

    assert data == {"type": "error", "error": "invalid_turn"}
