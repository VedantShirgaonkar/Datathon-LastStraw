"""
Connection test for Neo4j Aura.

Run this script to verify your Neo4j connection is working:
    python neo4j/neo4j_connection_test.py
    or from neo4j directory:
    python neo4j_connection_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from neo4j_client import Neo4jClient


def test_connection():
    """Test Neo4j connection and display status"""
    print("\n🔗 Testing Neo4j Aura Connection...")
    print("=" * 60)
    
    try:
        client = Neo4jClient()
        
        # Test connection
        info = client.verify_connection()
        
        if info["connected"]:
            print("✅ Connection successful!")
            print(f"\n📊 Database Information:")
            print(f"   URI:      {info.get('uri', 'N/A')}")
            print(f"   Database: {info.get('database', 'N/A')}")
            print(f"   Name:     {info.get('name', 'N/A')}")
            print(f"   Version:  {info.get('version', 'N/A')}")
            print(f"   Edition:  {info.get('edition', 'N/A')}")
            
            # Get statistics
            print(f"\n📈 Database Statistics:")
            stats = client.get_database_stats()
            print(f"   Total Nodes:         {stats['total_nodes']}")
            print(f"   Total Relationships: {stats['total_relationships']}")
            
            if stats['labels']:
                print(f"   Node Labels:         {', '.join(stats['labels'])}")
            else:
                print(f"   Node Labels:         (empty - no data yet)")
            
            if stats['relationship_types']:
                print(f"   Relationship Types:  {', '.join(stats['relationship_types'])}")
            else:
                print(f"   Relationship Types:  (empty - no data yet)")
            
            print("\n✅ Neo4j is ready to use!")
            return True
            
        else:
            print("❌ Connection failed!")
            print(f"   Error: {info.get('error', 'Unknown error')}")
            return False
    
    except ValueError as e:
        print("❌ Configuration Error!")
        print(f"   {e}")
        print("\n💡 Tip: Copy .env.example to .env and add your Neo4j credentials")
        return False
    
    except ConnectionError as e:
        print("❌ Connection Error!")
        print(f"   {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Check if your Neo4j Aura instance is running (green status)")
        print("   2. Verify the URI in .env matches your instance")
        print("   3. Ensure your password is correct")
        return False
    
    except Exception as e:
        print("❌ Unexpected Error!")
        print(f"   {type(e).__name__}: {e}")
        return False
    
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)
