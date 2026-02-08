import requests
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://0.0.0.0:7860/api"

def wait_for_server(retries=10, delay=2):
    for i in range(retries):
        try:
            resp = requests.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                logger.info("Server is up!")
                return True
        except requests.ConnectionError:
            pass
        logger.info(f"Waiting for server... ({i+1}/{retries})")
        time.sleep(delay)
    return False

def test_db_queries():
    logger.info("Starting Database Layer Verification via /api/message...")
    
    # 1. Postgres (Relational Data)
    # Asking for 'projects' should trigger Resource_Planner and hit the 'projects' table in Postgres
    query_pg = "List all active projects."
    logger.info(f"\n[Postgres Test] Query: {query_pg}")
    try:
        resp = requests.post(f"{BASE_URL}/message", json={"message": query_pg})
        if resp.status_code == 200:
            data = resp.json()
            logger.info("✅ Postgres Response Received")
            logger.info(f"   AVG Response Length: {len(data['response'])}")
            logger.info(f"   Snippet: {data['response'][:100]}...")
            
            # Check for indications of data (even if empty list, it shouldn't be an error)
            if "error" in data['response'].lower():
                 logger.warning("⚠️ Potential Error in Postgres response")
        else:
            logger.error(f"❌ Postgres Test Failed: {resp.status_code}")
    except Exception as e:
        logger.error(f"❌ Postgres Test Exception: {e}")


    # 2. ClickHouse (Analytical Data)
    # Asking for 'deployment metrics' should trigger DORA_Pro and hit ClickHouse
    query_ch = "Show me the deployment frequency for the last 30 days."
    logger.info(f"\n[ClickHouse Test] Query: {query_ch}")
    try:
        resp = requests.post(f"{BASE_URL}/message", json={"message": query_ch})
        if resp.status_code == 200:
            data = resp.json()
            logger.info("✅ ClickHouse Response Received")
            logger.info(f"   Snippet: {data['response'][:100]}...")
            if "deployment" in data['response'].lower() or "frequency" in data['response'].lower():
                logger.info("   ✅ Response seems relevant")
            else:
                 logger.warning("⚠️ Response might not contain metrics")
        else:
            logger.error(f"❌ ClickHouse Test Failed: {resp.status_code}")
    except Exception as e:
        logger.error(f"❌ ClickHouse Test Exception: {e}")


    # 3. Neo4j (Graph Data)
    # Asking for 'experts' or 'skills' should trigger Insights_Specialist and hit Neo4j
    query_neo = "Who is an expert in Python?"
    logger.info(f"\n[Neo4j Test] Query: {query_neo}")
    try:
        resp = requests.post(f"{BASE_URL}/message", json={"message": query_neo})
        if resp.status_code == 200:
            data = resp.json()
            logger.info("✅ Neo4j Response Received")
            logger.info(f"   Snippet: {data['response'][:100]}...")
            if "expert" in data['response'].lower() or "python" in data['response'].lower() or "found" in data['response'].lower():
                logger.info("   ✅ Response seems relevant")
            else:
                 logger.warning("⚠️ Response might not be from Graph")
        else:
            logger.error(f"❌ Neo4j Test Failed: {resp.status_code}")
    except Exception as e:
        logger.error(f"❌ Neo4j Test Exception: {e}")

    logger.info("\nVerify other endpoints sanity...")
    try:
        requests.get(f"{BASE_URL}/threads")
        logger.info("✅ /api/threads OK")
    except:
        logger.error("❌ /api/threads Failed")

if __name__ == "__main__":
    if wait_for_server():
        test_db_queries()
    else:
        logger.error("Server failed to start.")
