import uuid

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_signup_and_profile():
    email = f"deploy-test-{uuid.uuid4()}@example.com"
    payload = {
        "email": email,
        "password": "secret123",
        "full_name": "Deployment Tester",
        "confirm_password": "secret123",
    }
    signup = client.post("/api/auth/signup", json=payload)
    assert signup.status_code == 200, signup.text
    data = signup.json()
    assert "token" in data
    assert data["user"]["email"] == email

    token = data["token"]
    profile = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200, profile.text
    assert profile.json()["email"] == email


def test_signup_requires_matching_confirm_password():
    email = f"confirm-check-{uuid.uuid4()}@example.com"
    payload = {
        "email": email,
        "password": "secret123",
        "full_name": "Needs Confirmation",
        "confirm_password": "different-password",
    }

    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 400, response.text
    assert "confirm" in response.json()["detail"].lower()


def test_login_rejects_unregistered_email_with_valid_email_message():
    payload = {
        "email": f"missing-user-{uuid.uuid4()}@example.com",
        "password": "secret123",
        "full_name": "",
        "confirm_password": "secret123",
    }

    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 401, response.text
    assert "valid email" in response.json()["detail"].lower()
