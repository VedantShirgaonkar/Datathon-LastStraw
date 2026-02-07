"""
Connection test for ClickHouse Cloud.

Run this script to verify your ClickHouse connection is working:
    python clickhouse/clickhouse_connection_test.py
    or from clickhouse directory:
    python clickhouse_connection_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clickhouse_client import ClickHouseClient


def test_connection():
    """Test ClickHouse connection and display status"""
    print("\n🔗 Testing ClickHouse Cloud Connection...")
    print("=" * 60)
    
    try:
        client = ClickHouseClient()
        
        # Test connection
        info = client.verify_connection()
        
        if not info.get('connected'):
            print(f"\n❌ Connection failed!")
            print(f"   Error: {info.get('error')}")
            print("\n💡 Troubleshooting:")
            print("   1. Check your CLICKHOUSE_* variables in .env file")
            print("   2. Verify your ClickHouse Cloud service is running")
            print("   3. Check IP whitelist in ClickHouse Cloud console")
            print("   4. Ensure port 8443 (HTTPS) is used")
            return False
        
        print("\n✅ Connection successful!")
        print("\n📊 Database Information:")
        print(f"   Host:     {info['host']}")
        print(f"   Port:     8443 (HTTPS)")
        print(f"   Database: {info['database']}")
        print(f"   Version:  {info['version']}")
        
        # Check if schema exists
        print("\n📋 Checking schema...")
        tables = client.query("SHOW TABLES")
        
        if not tables:
            print("   ⚠️  No tables found. Run schema setup:")
            print("      python clickhouse/clickhouse_schema.py")
        else:
            print(f"   ✓ Found {len(tables)} table(s):")
            for table in tables:
                print(f"      - {table['name']}")
            
            # Check events table
            if any(t['name'] == 'events' for t in tables):
                count = client.get_event_count()
                print(f"\n📈 Database Statistics:")
                print(f"   Total Events: {count:,}")
                
                # Show recent events if any exist
                if count > 0:
                    print(f"\n🔍 Recent Events (last 5):")
                    recent = client.get_recent_events(limit=5)
                    for event in recent:
                        print(f"      - {event['timestamp']} | {event['source']:8} | "
                              f"{event['event_type']:15} | {event['actor_id']}")
        
        print("\n" + "=" * 60)
        print("✅ ClickHouse is ready to use!")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Common issues:")
        print("   1. Missing credentials in .env file")
        print("   2. Invalid host or password")
        print("   3. IP not whitelisted in ClickHouse Cloud")
        print("   4. Service not running")
        print("\nCheck CLICKHOUSE_SETUP_GUIDE.md for detailed setup instructions.")
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
