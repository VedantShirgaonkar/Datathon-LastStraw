"""
Test AWS MSK Connection

This script tests connectivity to the AWS MSK cluster.
Note: MSK requires your machine to be in the same VPC or have network access.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import os
from dotenv import load_dotenv
from kafka import KafkaConsumer, KafkaAdminClient
from kafka.errors import KafkaError, NoBrokersAvailable
import ssl

load_dotenv()


def test_msk_connection():
    """Test connection to AWS MSK cluster"""
    
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").split(",")
    topics = os.getenv("KAFKA_TOPICS", "").split(",")
    group_id = os.getenv("KAFKA_GROUP_ID", "database-agent-group")
    security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "SSL")
    ssl_enabled = os.getenv("KAFKA_SSL_ENABLED", "true").lower() == "true"
    
    print("=" * 60)
    print("AWS MSK Connection Test")
    print("=" * 60)
    print(f"\nBootstrap Servers:")
    for server in bootstrap_servers:
        print(f"  - {server}")
    print(f"\nTopics: {topics}")
    print(f"Group ID: {group_id}")
    print(f"Security Protocol: {security_protocol}")
    print(f"SSL Enabled: {ssl_enabled}")
    print("=" * 60)
    
    # Build consumer config
    consumer_config = {
        'bootstrap_servers': bootstrap_servers,
        'group_id': group_id,
        'auto_offset_reset': 'latest',
        'enable_auto_commit': False,
        'consumer_timeout_ms': 10000,  # 10 second timeout
    }
    
    # Add SSL config for MSK
    if ssl_enabled:
        consumer_config.update({
            'security_protocol': security_protocol,
            'ssl_check_hostname': True,
        })
    
    print("\n1. Testing broker connectivity...")
    
    try:
        # Try to create a consumer and connect
        consumer = KafkaConsumer(**consumer_config)
        
        # Subscribe to topics
        consumer.subscribe([t.strip() for t in topics])
        
        print("   ✅ Connected to MSK cluster!")
        
        # List available topics
        print("\n2. Checking available topics...")
        available_topics = consumer.topics()
        print(f"   ✅ Found {len(available_topics)} topics:")
        for topic in sorted(available_topics):
            marker = "  ← subscribed" if topic in topics else ""
            print(f"      - {topic}{marker}")
        
        # Try to poll for messages
        print("\n3. Polling for messages (10 second timeout)...")
        messages = consumer.poll(timeout_ms=10000)
        
        if messages:
            total_msgs = sum(len(msgs) for msgs in messages.values())
            print(f"   ✅ Received {total_msgs} messages!")
            
            for topic_partition, msgs in messages.items():
                print(f"\n   Topic: {topic_partition.topic}, Partition: {topic_partition.partition}")
                for msg in msgs[:3]:  # Show first 3 messages
                    print(f"      Offset: {msg.offset}")
                    print(f"      Value: {msg.value[:200]}..." if len(msg.value) > 200 else f"      Value: {msg.value}")
        else:
            print("   ⚠️  No messages received (topics may be empty)")
            print("   This is normal if no events have been sent recently.")
        
        consumer.close()
        
        print("\n" + "=" * 60)
        print("✅ MSK CONNECTION TEST PASSED")
        print("=" * 60)
        print("\nYou can now run the full Kafka consumer:")
        print("  python agent/kafka_consumer.py")
        
        return True
        
    except NoBrokersAvailable as e:
        print(f"\n   ❌ Cannot connect to MSK brokers!")
        print(f"\n   Error: {e}")
        print("\n   Possible causes:")
        print("   1. Your machine is not in the same VPC as MSK")
        print("   2. Security group doesn't allow inbound traffic")
        print("   3. MSK cluster is not running")
        print("\n   Solutions:")
        print("   - Run from an EC2 instance in VPC: vpc-0d21a65998db90c76")
        print("   - Use VPN/VPC peering to access MSK")
        print("   - Add your IP to security group: sg-0707335f229929c58")
        return False
        
    except KafkaError as e:
        print(f"\n   ❌ Kafka error: {e}")
        return False
        
    except Exception as e:
        print(f"\n   ❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_test_event():
    """Send a test event to the ingestion API"""
    import requests
    
    print("\n" + "=" * 60)
    print("Sending Test Event via Ingestion API")
    print("=" * 60)
    
    base_url = "https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com"
    
    # Send a test GitHub push event
    test_event = {
        "ref": "refs/heads/main",
        "commits": [
            {
                "id": "test123",
                "message": "Test commit from DataThon agent",
                "author": {"name": "DataThon Bot"}
            }
        ],
        "pusher": {"name": "datathon-test"},
        "repository": {"name": "test-repo", "full_name": "datathon/test-repo"}
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "push"
    }
    
    print(f"\nSending to: {base_url}/ingest/github")
    print(f"Event: push")
    
    try:
        response = requests.post(
            f"{base_url}/ingest/github",
            json=test_event,
            headers=headers,
            timeout=10
        )
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200:
            print("\n✅ Test event sent successfully!")
            print("The event should appear in the Kafka consumer shortly.")
        else:
            print("\n⚠️  Event may not have been processed correctly.")
            
    except Exception as e:
        print(f"\n❌ Failed to send test event: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test AWS MSK connection")
    parser.add_argument("--send-event", action="store_true", help="Send a test event via ingestion API")
    args = parser.parse_args()
    
    if args.send_event:
        send_test_event()
    else:
        success = test_msk_connection()
        
        if not success:
            print("\n💡 Tip: You can send a test event via the ingestion API:")
            print("   python test_msk_connection.py --send-event")
