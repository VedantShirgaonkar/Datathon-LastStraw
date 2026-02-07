# AI Agent Integration Guide

## Quick Start

Your AI Agent Lambda needs:

- **VPC**: `vpc-0d21a65998db90c76`
- **Security Group**: `sg-0707335f229929c58`
- **Kafka Topics**: `events.github`, `events.jira`, `events.notion`

---

# Sending Events to Kafka (Ingestion API)

**Base URL**: `https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com`

## GitHub Events

### Push Event

```bash
curl -X POST https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com/ingest/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{
    "ref": "refs/heads/main",
    "commits": [
      {"id": "abc123", "message": "Fixed login bug", "author": {"name": "User"}}
    ],
    "pusher": {"name": "username"},
    "repository": {"name": "repo-name", "full_name": "owner/repo"}
  }'
```

### Pull Request Event

```bash
curl -X POST https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com/ingest/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "number": 42,
    "pull_request": {
      "title": "Add new feature",
      "body": "Description",
      "user": {"login": "username"},
      "head": {"ref": "feature"},
      "base": {"ref": "main"}
    }
  }'
```

### Issue Event

```bash
curl -X POST https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com/ingest/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d '{
    "action": "opened",
    "issue": {
      "number": 15,
      "title": "Bug report",
      "body": "Bug description",
      "user": {"login": "reporter"}
    }
  }'
```

## Jira Events

### Issue Created

```bash
curl -X POST https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com/ingest/jira \
  -H "Content-Type: application/json" \
  -d '{
    "webhookEvent": "jira:issue_created",
    "issue": {
      "key": "PROJ-123",
      "fields": {
        "summary": "Bug title",
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "status": {"name": "To Do"}
      }
    }
  }'
```

### Issue Updated

```bash
curl -X POST https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com/ingest/jira \
  -H "Content-Type: application/json" \
  -d '{
    "webhookEvent": "jira:issue_updated",
    "issue": {"key": "PROJ-123", "fields": {"status": {"name": "Done"}}},
    "changelog": {
      "items": [{"field": "status", "fromString": "In Progress", "toString": "Done"}]
    }
  }'
```

## Notion Events

### Page Created

```bash
curl -X POST https://kbhlvvq5dj.execute-api.ap-south-1.amazonaws.com/ingest/notion \
  -H "Content-Type: application/json" \
  -d '{
    "type": "page_created",
    "page": {"id": "abc123", "title": "Meeting Notes"},
    "user": {"name": "Vedant"}
  }'
```

---

# Event Formats Received from Kafka

## Event Wrapper

```json
{
  "event_id": "uuid",
  "source": "github|jira|notion",
  "event_type": "push|jira:issue_created|...",
  "timestamp": "2026-02-07T12:56:27Z",
  "raw": {
    /* original payload */
  }
}
```

## GitHub Events

### Push

```json
{
  "source": "github",
  "event_type": "push",
  "raw": {
    "ref": "refs/heads/main",
    "commits": [
      { "id": "sha", "message": "Fixed bug", "author": { "name": "User" } }
    ],
    "repository": { "name": "repo", "full_name": "owner/repo" }
  }
}
```

### Pull Request

```json
{
  "source": "github",
  "event_type": "pull_request",
  "raw": {
    "action": "opened|closed|merged",
    "number": 42,
    "pull_request": {
      "title": "Feature",
      "merged": true,
      "user": { "login": "user" }
    }
  }
}
```

### Issue

```json
{
  "source": "github",
  "event_type": "issues",
  "raw": {
    "action": "opened|closed",
    "issue": { "number": 15, "title": "Bug", "user": { "login": "reporter" } }
  }
}
```

## Jira Events

### Issue Created

```json
{
  "source": "jira",
  "event_type": "jira:issue_created",
  "raw": {
    "issue": {
      "key": "PROJ-123",
      "fields": {
        "summary": "Title",
        "priority": { "name": "High" },
        "status": { "name": "To Do" }
      }
    }
  }
}
```

### Issue Updated

```json
{
  "source": "jira",
  "event_type": "jira:issue_updated",
  "raw": {
    "issue": { "key": "PROJ-123" },
    "changelog": {
      "items": [
        { "field": "status", "fromString": "To Do", "toString": "Done" }
      ]
    }
  }
}
```

---

# Lambda Handler

```python
import json, base64

def lambda_handler(event, context):
    for topic, records in event['records'].items():
        for record in records:
            data = json.loads(base64.b64decode(record['value']))
            source = data['source']
            raw = data['raw']

            if source == "github":
                if data['event_type'] == "push":
                    for commit in raw['commits']:
                        print(f"Commit: {commit['message']}")
            elif source == "jira":
                print(f"Issue: {raw['issue']['key']}")

    return {"status": "ok"}
```

---

# Executor Commands

```python
import boto3, json

lambda_client = boto3.client('lambda', region_name='ap-south-1')

def execute_command(target, action, payload):
    response = lambda_client.invoke(
        FunctionName='datathon-executor',
        Payload=json.dumps({"command": {"target": target, "action": action, "payload": payload}})
    )
    return json.loads(response['Payload'].read())
```

## Jira

```python
execute_command("jira", "create_issue", {"project_key": "PROJ", "summary": "Title", "issue_type": "Bug"})
execute_command("jira", "add_comment", {"issue_key": "PROJ-123", "body": "Comment"})
execute_command("jira", "assign_issue", {"issue_key": "PROJ-123", "assignee": "john"})
```

## GitHub

```python
execute_command("github", "create_issue", {"owner": "user", "repo": "repo", "title": "Title"})
execute_command("github", "add_comment", {"owner": "user", "repo": "repo", "issue_number": 1, "body": "Comment"})
execute_command("github", "close_issue", {"owner": "user", "repo": "repo", "issue_number": 1})
```

## Notion

```python
execute_command("notion", "create_page", {"parent_id": "db-id", "title": "Task", "title_property": "Name"})
execute_command("notion", "update_status", {"page_id": "id", "status": "Done"})
execute_command("notion", "assign_task", {"page_id": "id", "assignee": "Name", "priority": "High", "deadline": "2026-02-15"})
```

---

## MSK Connection

```
Brokers: b-1.datathonevents.kzbxr0.c2.kafka.ap-south-1.amazonaws.com:9094,b-2...
Security: TLS/SSL | VPC: vpc-0d21a65998db90c76
```
