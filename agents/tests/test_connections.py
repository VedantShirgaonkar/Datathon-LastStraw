"""
Test script for database connections.
Run this to verify all database connections are working.
"""

import sys
import os

# Add the parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.logger import get_logger, PhaseLogger
from agents.utils.config import load_config
from agents.utils.db_clients import test_all_connections, get_postgres_client, close_all_connections

logger = get_logger(__name__, "TEST")


def main():
    """Run all database connection tests."""
    logger.info("=" * 60)
    logger.info("Starting Database Connection Tests")
    logger.info("=" * 60)
    
    try:
        # Load configuration
        with PhaseLogger(logger, "Configuration Loading"):
            config = load_config("/Users/rahul/Desktop/Datathon/.env")
            logger.info(f"PostgreSQL Host: {config.postgres.host}")
            logger.info(f"Neo4j URI: {config.neo4j.uri}")
            logger.info(f"ClickHouse Host: {config.clickhouse.host}")
        
        # Test all connections
        results = test_all_connections()
        
        # Test a sample PostgreSQL query
        with PhaseLogger(logger, "Sample PostgreSQL Query"):
            pg = get_postgres_client()
            users = pg.execute_query("SELECT id, name, email, role FROM users LIMIT 3")
            logger.info(f"Found {len(users)} users:")
            for user in users:
                logger.info(f"  - {user['name']} ({user['role']})")
        
        # Summary
        logger.info("=" * 60)
        logger.info("Test Results Summary:")
        for db, status in results.items():
            status_str = "✓ PASS" if status else "✗ FAIL"
            logger.info(f"  {db}: {status_str}")
        logger.info("=" * 60)
        
        return all(results.values())
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        close_all_connections()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
