"""
Test webhook endpoints with sample payloads.

Run this script to test the webhook server with realistic GitHub, Jira, and Notion events.
"""

import requests
import json
import hmac
import hashlib
from datetime import datetime


# Configuration
WEBHOOK_BASE_URL = "http://localhost:8000"
GITHUB_SECRET = "your_github_webhook_secret_here"  # Must match .env


def sign_github_payload(payload_body: bytes, secret: str) -> str:
    """Generate GitHub webhook signature"""
    mac = hmac.new(secret.encode(), msg=payload_body, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_github_webhook():
    """Test GitHub PR merged webhook"""
    print("\n🔵 Testing GitHub Webhook...")
    
    payload = {
        "action": "closed",
        "number": 42,
        "pull_request": {
            "title": "Add OAuth2 authentication",
            "state": "closed",
            "merged": True,
            "merged_at": datetime.utcnow().isoformat() + "Z",
            "user": {
                "login": "johndoe",
                "email": "john@company.com"
            },
            "head": {
                "ref": "feature-oauth",
                "sha": "abc123def456"
            },
            "base": {
                "ref": "main"
            },
            "html_url": "https://github.com/company/repo/pull/42",
            "additions": 150,
            "deletions": 20,
            "changed_files": 5
        },
        "repository": {
            "name": "api-service",
            "full_name": "company/api-service"
        }
    }
    
    payload_json = json.dumps(payload)
    payload_bytes = payload_json.encode()
    
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": sign_github_payload(payload_bytes, GITHUB_SECRET)
    }
    
    response = requests.post(
        f"{WEBHOOK_BASE_URL}/webhooks/github",
        data=payload_bytes,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")


def test_jira_webhook():
    """Test Jira issue updated webhook"""
    print("\n🟠 Testing Jira Webhook...")
    
    payload = {
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "PROJ-123",
            "fields": {
                "summary": "Fix login bug",
                "description": "Users cannot log in with special characters in password",
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "status": {"name": "In Progress"},
                "assignee": {
                    "displayName": "John Doe",
                    "emailAddress": "john@company.com"
                },
                "reporter": {
                    "displayName": "Jane Smith",
                    "emailAddress": "jane@company.com"
                }
            }
        },
        "changelog": {
            "items": [
                {
                    "field": "status",
                    "fromString": "To Do",
                    "toString": "In Progress"
                }
            ]
        }
    }
    
    response = requests.post(
        f"{WEBHOOK_BASE_URL}/webhooks/jira",
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")


def test_notion_webhook():
    """Test Notion page updated webhook"""
    print("\n🟣 Testing Notion Webhook...")
    
    payload = {
        "type": "page_updated",
        "page": {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "created_time": "2026-02-01T10:00:00.000Z",
            "last_edited_time": datetime.utcnow().isoformat() + "Z",
            "properties": {
                "Name": {
                    "title": [{"text": {"content": "Q1 2026 Roadmap"}}]
                },
                "Status": {
                    "select": {"name": "In Progress"}
                },
                "Project": {
                    "select": {"name": "API Gateway"}
                }
            }
        }
    }
    
    response = requests.post(
        f"{WEBHOOK_BASE_URL}/webhooks/notion",
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")


def test_health_check():
    """Test server health check"""
    print("\n✅ Testing Health Check...")
    
    response = requests.get(f"{WEBHOOK_BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Webhook Server Test Suite")
    print("=" * 60)
    
    try:
        test_health_check()
        test_github_webhook()
        test_jira_webhook()
        test_notion_webhook()
        
        print("=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to webhook server")
        print("Make sure the server is running:")
        print("  python webhook_server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")
