from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_signup_and_profile():
    payload = {
        "email": "deploy-test@example.com",
        "password": "secret123",
        "full_name": "Deployment Tester",
    }
    signup = client.post("/api/auth/signup", json=payload)
    assert signup.status_code == 200, signup.text
    data = signup.json()
    assert "token" in data
    assert data["user"]["email"] == "deploy-test@example.com"

    token = data["token"]
    profile = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200, profile.text
    assert profile.json()["email"] == "deploy-test@example.com"
