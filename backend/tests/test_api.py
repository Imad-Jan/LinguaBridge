from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_save_configuration_without_external_validation():
    response = client.post(
        "/api/config",
        json={
            "public_base_url": "https://calls.example.com",
            "twilio_account_sid": "AC" + "1" * 32,
            "twilio_auth_token": "test-token-value",
            "gemini_api_key": "gemini-test",
            "soniox_api_key": "soniox-test",
            "validate_credentials": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["config_id"]
    assert body["twilio"]["valid"] is None
    assert body["gemini"]["configured"] is True


def test_e164_validation_rejects_local_number():
    config = client.post(
        "/api/config",
        json={
            "public_base_url": "https://calls.example.com",
            "twilio_account_sid": "AC" + "1" * 32,
            "twilio_auth_token": "test-token-value",
            "gemini_api_key": "gemini-test",
            "validate_credentials": False,
        },
    ).json()
    response = client.post(
        "/api/calls/prepare",
        json={
            "config_id": config["config_id"],
            "provider": "gemini",
            "from_number": "03001234567",
            "to_number": "+14155552671",
            "caller_language": "ur",
            "callee_language": "en",
        },
    )
    assert response.status_code == 422

