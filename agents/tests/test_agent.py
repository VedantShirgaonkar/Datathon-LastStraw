"""
Test script for the Supervisor Agent.
Runs a few test queries to verify the agent works end-to-end.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.logger import get_logger, PhaseLogger
from agents.utils.config import load_config
from agents.utils.db_clients import close_all_connections
from agents.supervisor import get_supervisor

logger = get_logger(__name__, "AGENT_TEST")


TEST_QUERIES = [
    ("Simple developer lookup", "Who is Priya Sharma?"),
    ("Team listing", "List all developers on the Platform Engineering team"),
    ("DORA metrics", "What are the deployment metrics for the API Gateway project?"),
]


def main():
    """Run agent tests."""
    logger.info("=" * 60)
    logger.info("Starting Agent Integration Tests")
    logger.info("=" * 60)
    
    try:
        # Load config
        with PhaseLogger(logger, "Configuration"):
            load_config("/Users/rahul/Desktop/Datathon/.env")
        
        # Initialize supervisor
        with PhaseLogger(logger, "Agent Initialization"):
            supervisor = get_supervisor()
            supervisor.initialize()
            logger.info("✓ Supervisor agent initialized")
        
        # Run test queries
        results = []
        for test_name, query in TEST_QUERIES:
            logger.info(f"\n{'─' * 40}")
            logger.info(f"Test: {test_name}")
            logger.info(f"Query: {query}")
            logger.info("─" * 40)
            
            try:
                with PhaseLogger(logger, f"Query: {test_name}"):
                    response = supervisor.query(query)
                    
                    # Check if we got a meaningful response
                    has_content = len(response) > 50
                    no_error = "error" not in response.lower() or "no error" in response.lower()
                    
                    if has_content and no_error:
                        logger.info(f"✓ Test passed - Got {len(response)} character response")
                        results.append((test_name, True, response[:200]))
                    else:
                        logger.warning(f"⚠ Test may have issues - Response: {response[:100]}")
                        results.append((test_name, False, response[:200]))
                        
            except Exception as e:
                logger.error(f"✗ Test failed: {e}")
                results.append((test_name, False, str(e)))
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Test Results Summary:")
        logger.info("=" * 60)
        
        passed = sum(1 for _, success, _ in results if success)
        total = len(results)
        
        for test_name, success, preview in results:
            status = "✓ PASS" if success else "✗ FAIL"
            logger.info(f"  {test_name}: {status}")
            logger.info(f"    Response preview: {preview[:80]}...")
        
        logger.info(f"\nTotal: {passed}/{total} tests passed")
        logger.info("=" * 60)
        
        return passed == total
        
    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        close_all_connections()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
