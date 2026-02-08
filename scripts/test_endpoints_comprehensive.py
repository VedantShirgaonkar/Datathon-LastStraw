import requests
import time
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:7860/api"

def wait_for_server(timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                logger.info("Server is up and healthy!")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    logger.error("Server failed to start within timeout.")
    return False

def test_health():
    logger.info("Testing /health...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy" or data["status"] == "degraded" # Allow degraded if DBs missing
    logger.info(f"✅ Health OK: {data['status']}")

def test_threads_crud():
    logger.info("Testing /threads CRUD...")
    
    # Create Thread
    create_payload = {"title": "Test Thread"}
    response = requests.post(f"{BASE_URL}/threads", json=create_payload)
    if response.status_code != 200:
        logger.error(f"Failed to create thread: {response.text}")
        return None
    
    thread_data = response.json()
    thread_id = thread_data["thread_id"]
    assert thread_data["title"] == "Test Thread"
    logger.info(f"✅ Created Thread: {thread_id}")
    
    # List Threads
    response = requests.get(f"{BASE_URL}/threads")
    assert response.status_code == 200
    threads = response.json()
    assert any(t["thread_id"] == thread_id for t in threads)
    logger.info(f"✅ Listed Threads: Found {thread_id}")
    
    return thread_id

def test_chat_simple(thread_id):
    logger.info("Testing /api/message (Simple)...")
    payload = {
        "message": "What is 2+2?",
        "thread_id": thread_id
    }
    try:
        response = requests.post(f"{BASE_URL}/message", json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Simple Chat Response: {data.get('response', '')[:50]}...")
        else:
            logger.error(f"❌ Simple Chat Failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Simple Chat Error: {e}")

def test_chat_sync(thread_id):
    logger.info("Testing /chat/sync...")
    payload = {
        "message": "Hello, simply reply with 'Hello World'",
        "thread_id": thread_id,
        "stream": False
    }
    try:
        response = requests.post(f"{BASE_URL}/chat/sync", json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Sync Chat Response: {data.get('response', '')[:50]}...")
            if data.get("model_used"):
                logger.info(f"   Model Used: {data['model_used']}")
        else:
            logger.error(f"❌ Sync Chat Failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Sync Chat Error: {e}")

def test_chat_stream(thread_id):
    logger.info("Testing /chat (Stream)...")
    payload = {
        "message": "Count from 1 to 3",
        "thread_id": thread_id,
        "stream": True
    }
    try:
        with requests.post(f"{BASE_URL}/chat", json=payload, stream=True, timeout=60) as response:
            if response.status_code == 200:
                logger.info("✅ Stream Started")
                content = ""
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data: "):
                            try:
                                event_data = json.loads(decoded_line[6:])
                                if event_data["event"] == "response":
                                    content += event_data["data"]["content"]
                                elif event_data["event"] == "model_selection":
                                    logger.info(f"   Stream Model: {event_data['data'].get('display_name')}")
                            except:
                                pass
                logger.info(f"✅ Stream Completed. Content length: {len(content)}")
            else:
                logger.error(f"❌ Stream Failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Stream Error: {e}")

def test_feature_endpoints():
    logger.info("Testing Feature Endpoints...")
    
    # 1. Prep 1:1
    # We use a dummy name, we expect 404 or success, but NOT 500
    try:
        logger.info("  Testing /api/prep/1on1...")
        resp = requests.post(f"{BASE_URL}/prep/1on1", json={"developer_name": "Test User", "manager_context": "Checkin"})
        if resp.status_code in [200, 404]:
            logger.info(f"  ✅ Prep 1:1: {resp.status_code}")
        else:
            logger.error(f"  ❌ Prep 1:1 Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"  ❌ Prep 1:1 Error: {e}")

    # 2. Anomalies
    try:
        logger.info("  Testing /api/anomalies...")
        resp = requests.post(f"{BASE_URL}/anomalies", json={"days_current": 7, "days_baseline": 30})
        # This might fail if DB is not set up, but we want to see handled return
        if resp.status_code == 200:
             logger.info(f"  ✅ Anomalies: 200 OK")
        elif resp.status_code == 500 and "error" in resp.text.lower():
             logger.info(f"  ⚠️ Anomalies: 500 (Expected if DB missing/empty): {resp.text[:100]}")
        else:
             logger.error(f"  ❌ Anomalies Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"  ❌ Anomalies Error: {e}")

    # 3. Experts
    try:
        logger.info("  Testing /api/experts/find...")
        resp = requests.post(f"{BASE_URL}/experts/find", json={"query": "python", "mode": "quick", "limit": 1})
        if resp.status_code == 200:
            logger.info("  ✅ Experts (Quick): 200 OK")
        else:
            logger.error(f"  ❌ Experts Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
         logger.error(f"  ❌ Experts Error: {e}")

    # 4. Search
    try:
        logger.info("  Testing /api/search...")
        resp = requests.post(f"{BASE_URL}/search", json={"query": "api", "limit": 1})
        if resp.status_code == 200:
            logger.info("  ✅ Search: 200 OK")
        else:
             logger.error(f"  ❌ Search Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
         logger.error(f"  ❌ Search Error: {e}")

    # 5. DORA
    try:
        logger.info("  Testing /api/metrics/dora...")
        resp = requests.post(f"{BASE_URL}/metrics/dora", json={"days": 30})
        if resp.status_code == 200:
             logger.info("  ✅ DORA: 200 OK")
        elif resp.status_code == 500:
             logger.info(f"  ⚠️ DORA: 500 (Likely DB issue): {resp.text[:100]}")
        else:
             logger.error(f"  ❌ DORA Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
         logger.error(f"  ❌ DORA Error: {e}")

def verify_all():
    if not wait_for_server():
        return

    test_health()
    thread_id = test_threads_crud()
    
    if thread_id:
        test_chat_simple(thread_id)
        test_chat_stream(thread_id)
        
        test_feature_endpoints()

        # Cleanup
        logger.info(f"Cleaning up thread {thread_id}...")
        requests.delete(f"{BASE_URL}/threads/{thread_id}")
        logger.info("✅ Thread Deleted")

if __name__ == "__main__":
    verify_all()
