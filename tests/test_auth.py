import pytest

# Example using Pytest and Flask/FastAPI TestClient mock structure
@pytest.fixture
def api_client():
    """
    Replace this fixture with your actual backend app test client.
    Example for Flask: 
        from app import app
        return app.test_client()
    """
    # Placeholder mockup client for demonstration structure
    class DummyClient:
        def post(self, endpoint, json):
            if endpoint == "/api/auth/send-otp":
                if json.get("phone") == "+919876543210":
                    return DummyResponse(200, {"success": True, "message": "OTP sent successfully"})
                return DummyResponse(400, {"success": False, "message": "Invalid phone number"})
            
            elif endpoint == "/api/auth/verify-otp":
                if json.get("otp") == "123456":
                    return DummyResponse(200, {"success": True, "token": "mock_jwt_token_12345"})
                return DummyResponse(401, {"success": False, "message": "Invalid OTP"})
            
            return DummyResponse(404, {"message": "Not found"})

    class DummyResponse:
        def __init__(self, status_code, data):
            self.status_code = status_code
            self._data = data

        def get_json(self):
            return self._data

    return DummyClient()


def test_send_otp_success(api_client):
    """Test OTP request with a valid phone number."""
    payload = {"phone": "+919876543210"}
    response = api_client.post("/api/auth/send-otp", json=payload)
    
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["message"] == "OTP sent successfully"


def test_send_otp_invalid_phone(api_client):
    """Test OTP request with an invalid phone format."""
    payload = {"phone": "invalid_number"}
    response = api_client.post("/api/auth/send-otp", json=payload)
    
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False


def test_verify_otp_success(api_client):
    """Test verifying a correct OTP."""
    payload = {"phone": "+919876543210", "otp": "123456"}
    response = api_client.post("/api/auth/verify-otp", json=payload)
    
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "token" in data


def test_verify_otp_failure(api_client):
    """Test verifying an incorrect OTP."""
    payload = {"phone": "+919876543210", "otp": "000000"}
    response = api_client.post("/api/auth/verify-otp", json=payload)
    
    assert response.status_code == 401
    data = response.get_json()
    assert data["success"] is False
