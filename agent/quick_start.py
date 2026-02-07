"""
Quick start script for Database Agent.
Validates configuration and starts Kafka consumer.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv


def check_prerequisites():
    """Check if all prerequisites are met"""
    print("🔍 Checking prerequisites...")
    
    checks = []
    
    # Check .env file
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        print("✅ .env file found")
        checks.append(True)
        load_dotenv(env_path)
    else:
        print("❌ .env file not found")
        print("   Copy .env.example to .env and fill in credentials")
        checks.append(False)
    
    # Check required environment variables
    required_vars = [
        "FEATHERLESS_API_KEY",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "CLICKHOUSE_HOST",
        "CLICKHOUSE_USERNAME",
        "CLICKHOUSE_PASSWORD",
        "KAFKA_BOOTSTRAP_SERVERS"
    ]
    
    missing_vars = []
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var} configured")
            checks.append(True)
        else:
            print(f"❌ {var} not configured")
            missing_vars.append(var)
            checks.append(False)
    
    # Check Python packages
    try:
        import langchain
        print("✅ langchain installed")
        checks.append(True)
    except ImportError:
        print("❌ langchain not installed")
        print("   Run: uv pip install -r requirements.txt")
        checks.append(False)
    
    try:
        import langgraph
        print("✅ langgraph installed")
        checks.append(True)
    except ImportError:
        print("❌ langgraph not installed")
        print("   Run: uv pip install -r requirements.txt")
        checks.append(False)
    
    try:
        import neo4j
        print("✅ neo4j driver installed")
        checks.append(True)
    except ImportError:
        print("❌ neo4j driver not installed")
        print("   Run: uv pip install -r requirements.txt")
        checks.append(False)
    
    try:
        import clickhouse_connect
        print("✅ clickhouse-connect installed")
        checks.append(True)
    except ImportError:
        print("❌ clickhouse-connect not installed")
        print("   Run: uv pip install -r requirements.txt")
        checks.append(False)
    
    try:
        import kafka
        print("✅ kafka-python installed")
        checks.append(True)
    except ImportError:
        print("❌ kafka-python not installed")
        print("   Run: uv pip install -r requirements.txt")
        checks.append(False)
    
    return all(checks), missing_vars


def test_connections():
    """Test database connections"""
    print("\n🔗 Testing database connections...")
    
    # Test Neo4j
    try:
        from neo4j_db.neo4j_client import Neo4jClient
        client = Neo4jClient()
        client.verify_connection()
        client.close()
        print("✅ Neo4j connection successful")
    except Exception as e:
        print(f"❌ Neo4j connection failed: {e}")
        return False
    
    # Test ClickHouse
    try:
        from clickhouse.clickhouse_client import ClickHouseClient
        client = ClickHouseClient()
        version = client.get_server_version()
        client.close()
        print(f"✅ ClickHouse connection successful (v{version})")
    except Exception as e:
        print(f"❌ ClickHouse connection failed: {e}")
        return False
    
    return True


def start_agent():
    """Start the agent"""
    print("\n🚀 Starting Database Agent...")
    print("=" * 80)
    
    from agent.kafka_consumer import main
    main()


def main_cli():
    """Main CLI entry point"""
    print("=" * 80)
    print("DATABASE AGENT - QUICK START")
    print("=" * 80)
    print()
    
    # Run checks
    prereqs_ok, missing_vars = check_prerequisites()
    
    if not prereqs_ok:
        print("\n❌ Prerequisites not met")
        print("\nPlease fix the issues above and try again.")
        
        if missing_vars:
            print("\nMissing environment variables:")
            for var in missing_vars:
                print(f"  - {var}")
        
        print("\nSetup instructions:")
        print("  1. Copy .env.example to .env")
        print("  2. Fill in all required credentials")
        print("  3. Run: uv pip install -r requirements.txt")
        print("  4. Run this script again")
        
        return
    
    print("\n✅ All prerequisites met")
    
    # Test connections
    if not test_connections():
        print("\n❌ Database connections failed")
        print("\nPlease check your credentials in .env file")
        return
    
    print("\n✅ All connections successful")
    
    # Ask to start
    print("\n" + "=" * 80)
    response = input("Start Kafka consumer? (y/n): ")
    
    if response.lower() in ['y', 'yes']:
        start_agent()
    else:
        print("\nAgent not started. To start manually:")
        print("  python agent/kafka_consumer.py")


if __name__ == "__main__":
    try:
        main_cli()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
