from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_home_page():
    response = client.get("/")
    assert response.status_code == 200

def test_chat_history_empty():
    response = client.get("/messages/UserA/UserB")
    assert response.status_code == 200
    assert isinstance(response.json(), list)