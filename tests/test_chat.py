import pytest

@pytest.fixture
def chat_client():
    """Mock client for testing chat endpoints."""
    class DummyChatClient:
        def get(self, endpoint, headers=None):
            if endpoint == "/api/chats/contacts":
                return DummyResponse(200, {
                    "contacts": [
                        {"id": 1, "name": "John Doe", "status": "online"},
                        {"id": 2, "name": "Jane Smith", "status": "offline"}
                    ]
                })
            elif endpoint == "/api/chats/1/messages":
                return DummyResponse(200, {
                    "messages": [
                        {"sender": "John Doe", "text": "Hey! How is it going?", "timestamp": "10:42 AM"},
                        {"sender": "Me", "text": "All good bro!", "timestamp": "10:43 AM"}
                    ]
                })
            return DummyResponse(404, {})

        def post(self, endpoint, json, headers=None):
            if endpoint == "/api/chats/send":
                if json.get("message"):
                    return DummyResponse(201, {"success": True, "message_id": "msg_99"})
                return DummyResponse(400, {"success": False, "message": "Empty message"})
            return DummyResponse(404, {})

    class DummyResponse:
        def __init__(self, status_code, data):
            self.status_code = status_code
            self._data = data

        def get_json(self):
            return self._data

    return DummyChatClient()


def test_get_contacts_list(chat_client):
    """Test fetching contact list."""
    response = chat_client.get("/api/chats/contacts")
    assert response.status_code == 200
    data = response.get_json()
    assert "contacts" in data
    assert len(data["contacts"]) > 0


def test_get_chat_history(chat_client):
    """Test fetching message history for a contact."""
    response = chat_client.get("/api/chats/1/messages")
    assert response.status_code == 200
    data = response.get_json()
    assert "messages" in data
    assert len(data["messages"]) == 2


def test_send_message_success(chat_client):
    """Test sending a valid text message."""
    payload = {"receiver_id": 1, "message": "Hey! CSS is fixed now 🔥"}
    response = chat_client.post("/api/chats/send", json=payload)
    
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert "message_id" in data


def test_send_message_empty_fail(chat_client):
    """Test sending an empty message fails."""
    payload = {"receiver_id": 1, "message": ""}
    response = chat_client.post("/api/chats/send", json=payload)
    
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
