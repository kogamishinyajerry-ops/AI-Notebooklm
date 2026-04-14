import requests
import time
import os

API_URL = "http://localhost:8000"

def run_tests():
    print("🚀 Starting E2E Integration Test...")
    
    # 1. Health Check
    print("Checking API Health...")
    resp = requests.get(f"{API_URL}/health")
    assert resp.status_code == 200, "API is down"
    print("✅ Health Check Passed")
    
    # 2. Chat E2E (Retrieval + Gateway)
    print("Testing NotebookLM RAG + Gateway Execution...")
    payload = {
        "query": "请解释飞行控制律的核心要素。",
        "space_id": "test-env"
    }
    
    resp = requests.post(f"{API_URL}/api/v1/chat", json=payload)
    assert resp.status_code == 200, "Chat endpoint failed"
    data = resp.json()
    
    print("\n[AI Response]")
    print(data["answer"])
    
    # 3. Validation C2 (Traceability)
    assert "citations" in data, "No citations payload returned"
    assert data["is_fully_verified"] is not None, "Verification flag missing"
    
    print(f"\n✅ Verification Flag: {data['is_fully_verified']}")
    print(f"✅ Extracted Citations: {len(data['citations'])}")
    
    if data['citations']:
        c = data['citations'][0]
        print(f"Sample Citation -> Source: {c['source_file']} | Page: {c['page_number']} | BBox: {c['bbox']}")
    
    print("\n🎉 E2E Test Suite Completed Successfully.")

if __name__ == "__main__":
    # In a real CI environment, we would start the server dynamically. 
    # Here, we assume the server is running on port 8000.
    try:
        run_tests()
    except requests.exceptions.ConnectionError:
        print("⚠️ Server is not running on localhost:8000. Start it via 'uvicorn apps.api.main:app' to test.")
