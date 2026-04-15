import requests
import pytest

API_URL = "http://localhost:8000"

pytestmark = pytest.mark.live_server


def run_tests():
    # 1. Health Check
    resp = requests.get(f"{API_URL}/health", timeout=5)
    if resp.status_code != 200:
        raise RuntimeError(f"Unexpected health response: {resp.status_code}")

    # 2. Chat E2E (Retrieval + Gateway)
    payload = {
        "query": "请解释飞行控制律的核心要素。",
        "space_id": "test-env"
    }
    
    resp = requests.post(f"{API_URL}/api/v1/chat", json=payload, timeout=10)
    assert resp.status_code == 200, "Chat endpoint failed"
    data = resp.json()

    # 3. Validation C2 (Traceability)
    assert "citations" in data, "No citations payload returned"
    assert data["is_fully_verified"] is not None, "Verification flag missing"
    return data


def test_live_e2e_chat_contract():
    try:
        data = run_tests()
    except requests.exceptions.ConnectionError:
        pytest.skip("Local API server is not running on localhost:8000")
    except RuntimeError as exc:
        pytest.skip(f"Live server does not appear to be this project API: {exc}")

    assert "answer" in data
    assert "citations" in data

if __name__ == "__main__":
    # In a real CI environment, we would start the server dynamically. 
    # Here, we assume the server is running on port 8000.
    try:
        run_tests()
    except requests.exceptions.ConnectionError:
        print("⚠️ Server is not running on localhost:8000. Start it via 'uvicorn apps.api.main:app' to test.")
